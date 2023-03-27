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
    fr = po_db.lang('fr') # Important–need to create language callbacks only from
    it = po_db.lang('it') # statically known set of languages

    print('hello in French:', fr('hello'))
    print('hello in Italian:', it('hello'))

if __name__ == '__main__':
    # Using a context manager because it opens and closes DB
    # Using current directory for files to simplify
    with Podb(workdir='.') as po_db:
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

- `po.db`: this is the default filename used unless you pass in an override. It's
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

As I mentioned earlier, you need to create the language callbacks from a
statically known set of languages only:

```python
fr = po_db.lang('fr')
it = po_db.lang('it')
ja = po_db.lang('ja') # and so on
```

This is because the language names are injected directly into the database, so
allowing users to set whatever language names they like can lead to embarrassing
SQL injections.

Of course, you can dynamically select the language from the statically-known set,
e.g. here we are using the Flask framework:

```python
# app.py

from typing import Optional
from flask import Flask, g, render_template, request
from podb import Podb
import signal
import sys

# We don't have an entrypoint or blocking call that will keep the database open
# in a context manager, so set up the database open/close manually:

pos = Podb().__enter__()

def shutdown(signum, frame):
    pos._close()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

app = Flask(__name__)

# Statically-known set of language names
languages = {'fr-CA', 'fr', 'it', 'en-GB'}

@app.before_request
def accept_language():
    lang_name = request.accept_languages.best_match(languages, default='en')
    # Important: construct language objects only from statically-known set of
    # language names
    g.lang = pos.lang(lang_name) if lang_name in languages else pos.lang('en')
    g.lang_name = g.lang.id

@app.after_request
def content_language(resp):
    resp.content_language.add(g.lang_name)
    return resp

@app.route('/hello/')
@app.route('/hello/<name>')
def hello(name: Optional[str]=None):
    t = g.lang

    return render_template(
        'hello.html',
        lang=g.lang_name,
        name=name,
        # Translations all done in the handler, variables containing translated
        # strings passed into template.
        hello_from=t('Hello from'),
        hello=t('Hello'))
```

And the template which will be rendered:

```html
<!-- templates/hello.html -->

<!doctype html>
<html lang="{{ lang }}">
  <head>
    <title>Hello</title>
  </head>
  <body>
{% if name %}
    {{ hello }}, {{ name }}!
{% else %}
    {{ hello_from }} Flask!
{% endif %}
  </body>
</html>
```

Testing it out:

```
$ curl -i -H 'Accept-Language: fr' 'http://127.0.0.1:5000/hello/'
HTTP/1.1 200 OK
Server: Werkzeug/2.2.3 Python/3.9.6
Date: Mon, 27 Mar 2023 02:23:34 GMT
Content-Type: text/html; charset=utf-8
Content-Length: 136
Content-Language: fr
Connection: close

<!doctype html>
<html lang="fr">
  <head>
    <title>Hello</title>
  </head>
  <body>

    🇺🇸 Hello from Flask!

  </body>
</html>
```

Notice that the content negotiation is done by taking the `Accept-Language`
header into account, and the response header `Content-Language` shows that the
translation was done into the language `fr` (of course, in the beginning there is
no translation so the English message is rendered, just with a US flag prefixed
by default). If we ask for a language that's not supported:

```
$ curl -i -H 'Accept-Language: ja' 'http://127.0.0.1:5000/hello/'
HTTP/1.1 200 OK
Server: Werkzeug/2.2.3 Python/3.9.6
Date: Mon, 27 Mar 2023 02:24:33 GMT
Content-Type: text/html; charset=utf-8
Content-Length: 127
Content-Language: en
Connection: close

<!doctype html>
<html lang="en">
  <head>
    <title>Hello</title>
  </head>
  <body>

    Hello from Flask!

  </body>
</html>
```

We get back the default language which is `en`.
