## podb - simplified i18n/l10n .po file management with SQLite

Copyright 2023 Yawar Amin

This file is part of podb.

podb is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

podb is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
podb. If not, see <https://www.gnu.org/licenses/>.

## What

This is a proof of concept of trying to simplify translation management as much
as possible using SQLite. Traditionally internationalization/localization are
done with GNU gettext or its derivative technologies, and the workflow for
managing all the files needed (`.pot`, `.po`, `.mo`) is not great unless
everyone including the developers and translators all happen to be using GNU
Emacs with `gettext` mode.

This library aims to remove almost all the pain of juggling all these file
formats. The workflow should look like:

### Import and use the library

```python
from podb import Podb

def main(po_db: Podb):
    fr = po_db.lang('fr') # Important–need to know what languages you need
    it = po_db.lang('it')

    print('hello in French:', fr('hello'))
    print('hello in Italian:', it('hello'))

if __name__ == '__main__':
    # Using a context manager because it opens and closes DB
    with Podb('po.db') as po_db:
        main(po_db)
```

You will get this output:

```
hello in French: 🔴
hello in Italian: 🔴
```

(The `🔴` emoji is used as a strong visual indicator that the translation is
missing.)

### Manage files

After the script exits, you will find the following files in the working
directory:

- `po.db`: this is the filename you passed in to the `Podb()` constructor. It's
  the SQLite database created automatically to hold all the translations if it
  doesn't exist already. This is the source of truth for the translations in
  your project and you can commit this file in the repo as part of the
  development process.
- `fr.po`, `it.po`: these are meant to be sent to the translators directly. They
  are generated from the `po.db` file. Consider these to be exports which tell
  you what translations are needed. You can commit these into the repo if you
  want to, but it's not necessary.

When the translators send back the files with translations (i.e. `msgstr`)
filled in, just put the files in the working directory (in the same place they
are output above), and run your app. The `Podb` class will automatically read
all the filled-in entries from the files and upsert them into the database. The
script will output:

```
hello in French: bonjour
hello in Italian: bonguorno
```

The manual part of this is reduced to:

- You send the exported `.po` files to the translators
- You receive the translated `.po` files from the translators, place them in the
  working directory, and rerun the app.

Incidentally, the `po.db` file translations will look like:

```
sqlite> select * from po;
┌─────────────────────┬──────┬──────────┬───────┬─────────┬───────────┐
│     updated_at      │ ref  │ xcomment │  en   │   fr    │    it     │
├─────────────────────┼──────┼──────────┼───────┼─────────┼───────────┤
│ 2023-03-21 04:01:50 │ podb │          │ hello │ bonjour │ bonguorno │
└─────────────────────┴──────┴──────────┴───────┴─────────┴───────────┘
```

## Languages

As I mentioned earlier, you need to create the language callbacks beforehand:

```python
fr = po_db.lang('fr')
it = po_db.lang('it')
ja = po_db.lang('ja') # and so on
```

This is because the database needs to be updated to handle the languages that
your app uses, before it starts using them.

Of course, you can dynamically select the language e.g. suppose you use an HTTP
server framework, you can write a middleware like:

```python
class AcceptLanguage(Middleware):
    def __init__(self, po_db: Podb):
        self.lang_fr = po_db.lang('fr')
        self.lang_it = po_db.lang('it')
        self.lang_ja = po_db.lang('ja')

    # Simplified
    def handle(req: Request) -> Response:
        acceptLanguage = request.header('Accept-Language')
        contentLanguage = acceptLanguage

        if acceptLanguage == 'fr': req.lang = lang_fr
        elif acceptLanguage == 'it': req.lang = lang_it
        elif acceptLanguage == 'ja': req.lang = lang_ja
        else:
            contentLanguage = 'en'
            req.lang = lambda s: s # No translation

        res = self.next(req)
        res.set_header('Content-Language', contentLanguage)
    ...

accept_language = AcceptLanguage(po_db)
...
@accept_language
def get_stuff(req: Request) -> Response:
    return Response(req.lang('Here's some stuff'))
```

