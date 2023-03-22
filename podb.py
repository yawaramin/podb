import functools
import os
import polib
import sqlite3
from typing import Callable

MISSING = '🔴'
CREATE = '''create table if not exists po (
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
    return f'''begin;
    alter table po add column {id} text;
    create view {id}_po as
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
    where {id} is null;
commit;'''

def _msgstr(lang: str) -> str:
    return f'''select {lang}
from po
where en = ?
and xcomment = ?'''

def _po(lang: str) -> str:
    return f'''select entry from {lang}_po'''

def _upsert(lang: str) -> str:
    return f'''insert into po (updated_at, xcomment, en, {lang})
values (current_timestamp, ?, ?, ?)
on conflict (en, xcomment) do update set {lang} = excluded.{lang}'''

class Lang:
    def __init__(self, id: str, get_msgstr: Callable[[str, str, str], str]):
        self.id = id
        self.get_msgstr = get_msgstr

    def __call__(self, msgid: str, xcomment: str='', ref: str=__name__) -> str:
        return self.get_msgstr(msgid, xcomment, ref)

class Podb:
    def __init__(self, filename: str):
        self.filename = filename
        self.langs: list[str] = []

    def __enter__(self):
        self.db = sqlite3.connect(self.filename)
        self.db.execute(CREATE)
        self._read_pos()

        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self._close()

    def _close(self):
        self._write_pos()
        self.db.close()

    @functools.cache
    def lang(self, lang: str) -> Lang:
        '''
        Create and register a translator for a language `lang`. Should be
        formatted as e.g. `en` or `en_US` (underscore).

        WARNING: don't call this with untrusted user input as it can lead to SQL
        injection. Make sure you call it only with statically-known strings.
        '''
        if lang != 'en':
            self.langs.append(lang)
            self._check_lang(lang)

        backup_lang = lang.split('_')[0] if '_' in lang else None
        msgstr = _msgstr(lang)

        def get_msgstr(msgid: str, xcomment: str, ref: str) -> str:
            res = self.db.execute(msgstr, (msgid, xcomment))
            row = res.fetchone()

            if row is None:
                self.db.execute(ADD_ENTRY, (ref, xcomment, msgid))
                self.db.commit()

                return MISSING if backup_lang is None else self.lang(backup_lang)(msgid, xcomment, ref)

            if row[0] is None:
                return MISSING if backup_lang is None else self.lang(backup_lang)(msgid, xcomment, ref)

            return row[0]

        return Lang(lang, get_msgstr)

    def _check_lang(self, lang: str):
        if self.db.execute(HAS_LANG, (lang,)).fetchone()[0] == 0:
            self.db.executescript(_add_lang(lang))
            self.db.commit()

    def _write_pos(self):
        for lang in self.langs:
            with open(lang + '.po', 'w') as lang_po:
                for entry in self.db.execute(_po(lang)).fetchall():
                    lang_po.write(entry[0])

    def _read_pos(self):
        for file in os.listdir():
            if file.endswith('.po'):
                lang = file[:-3]
                for entry in polib.pofile(file):
                    msgstr = entry.msgstr
                    if msgstr == '':
                        msgstr = None

                    self.db.execute(
                        _upsert(lang),
                        (entry.comment, entry.msgid, msgstr))

        self.db.commit()