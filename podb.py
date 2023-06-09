import functools
import os
from os import path
from types import TracebackType
import polib
import sqlite3
from typing import Callable, Optional, Type

CREATE = '''pragma journal_mode=wal;
create table if not exists po (
    updated_at timestamp not null default current_timestamp,
    ref text,
    xcomment text not null default '',
    en text not null,
    primary key (en, xcomment)
)'''
HAS_LANG = '''select count(*)
from sqlite_schema
where name = ? || '_po'
'''
ADD_ENTRY = '''insert into po (updated_at, ref, xcomment, en)
values (current_timestamp, ?, ?, ?)'''

def _add_lang(id: str) -> str:
    '''
    Careful–this is directly interpolating the language name into the SQL query.
    Don't allow untrusted users to run this function. Make sure it's run only by
    internal tooling.
    '''
    return f'''alter table po add column "{id}" text;
    create view "{id}_po" as
    select
        iif(xcomment = '', '', '
#. ' || xcomment) ||
        iif(ref is null, '', '
#: ' || ref) ||
'
msgid "' ||
en ||
'"
msgstr ""
' as entry
    from po
    where "{id}" is null'''

def _msgstr(lang: str) -> str:
    return f'select "{lang}" from po where en = ?  and xcomment = ?'

def _po(lang: str) -> str:
    return f'select entry from "{lang}_po"'

def _upsert(lang: str) -> str:
    return f'''insert into po (updated_at, xcomment, en, "{lang}")
values (current_timestamp, ?, ?, ?)
on conflict (en, xcomment) do update set {lang} = excluded."{lang}"
'''

class Lang:
    def __init__(self, id: str, get_msgstr: Callable[[str, str, str], str]):
        self.id = id
        self.get_msgstr = get_msgstr

    def __call__(self, msgid: str, xcomment: str='', ref: str=__name__) -> str:
        return self.get_msgstr(msgid, xcomment, ref)

class Podb:
    def __init__(self, workdir: str='po', filename: str='po.db', missing: str='🇺🇸 '):
        '''
        Create or open the PO database in working directory `workdir` with name
        `filename`. For missing messages, translations will be returned prefixed
        with the string `missing`.
        '''
        self._wd = workdir
        self._filename = filename
        self._missing = missing
        self._langs: list[str] = []

    def __enter__(self):
        sqlite3.threadsafety = 3
        self._db = sqlite3.connect(path.join(self._wd, self._filename), check_same_thread=False)
        self._db.executescript(CREATE)
        self._read_pos()

        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]) -> Optional[bool]:
        self._close()

    def _close(self):
        self._write_pos()
        self._db.close()

    @functools.cache
    def lang(self, lang: str) -> Lang:
        '''
        Create and register a translator for a language `lang`. Should be
        formatted as e.g. `en` or `en_US` (underscore). Caches the `Lang`
        instances so is safe to call multiple times for the same language.

        WARNING: don't call this with untrusted user input as it can lead to SQL
        injection. Make sure you call it only with statically-known strings.

        Assumption: the base language for all translations is called 'en'.
        '''
        if lang == 'en': return Lang('en', lambda msgid, xcomment, ref: msgid)

        self._langs.append(lang)
        self._check_lang(lang)

        # E.g. en_GB backup is en
        backup_lang = lang.split('-')[0] if '-' in lang else None
        msgstr = _msgstr(lang)

        def get_msgstr(msgid: str, xcomment: str, ref: str) -> str:
            row = self._db.execute(msgstr, (msgid, xcomment)).fetchone()

            if row is None:
                self._db.execute(ADD_ENTRY, (ref, xcomment, msgid))
                self._db.commit()

                return self._missing + msgid if backup_lang is None else self.lang(backup_lang)(msgid, xcomment, ref)

            if row[0] is None:
                return self._missing + msgid if backup_lang is None else self.lang(backup_lang)(msgid, xcomment, ref)

            return row[0]

        return Lang(lang, get_msgstr)

    def _check_lang(self, lang: str):
        if self._db.execute(HAS_LANG, (lang,)).fetchone() == (0,):
            self._db.executescript(_add_lang(lang))
            self._db.commit()

    def _write_pos(self):
        for lang in self._langs:
            with open(path.join(self._wd, lang + '.po'), 'w') as lang_po:
                lang_po.write(f'''msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"X-Generator: https://github.com/yawaramin/podb\\n"
"Project-Id-Version: {self._filename}\\n"
"Language: {lang}\\n"
''')

                for (entry,) in self._db.execute(_po(lang)).fetchall():
                    lang_po.write(entry)

    def _read_pos(self):
        for file in os.listdir(self._wd):
            if file.endswith('.po'):
                po = polib.pofile(path.join(self._wd, file))
                upsert = _upsert(
                    po.metadata['Language']
                    if 'Language' in po.metadata
                    else file[:-3])

                for entry in po:
                    msgstr = entry.msgstr
                    if msgstr == '': continue

                    self._db.execute(
                        upsert,
                        (entry.comment, entry.msgid, msgstr))

        self._db.commit()
