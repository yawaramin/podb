from podb import Podb

def main(po_db: Podb):
    fr = po_db.lang('fr')
    en_GB = po_db.lang('en_GB')

    print('hello in British English:', en_GB('hello'))
    print('hello in French:', fr('hello'))
    print('meter in British English:', en_GB('meter'))
    print('meter in French:', fr('meter'))

if __name__ == '__main__':
    with Podb() as po_db:
        main(po_db)
