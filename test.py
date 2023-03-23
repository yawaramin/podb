from podb import Podb

def main(po_db: Podb):
    fr = po_db.lang('fr')
    en_GB = po_db.lang('en_GB')

    print('hello in French:', fr('hello'))
    print('hello in British English:', en_GB('hello'))
    print('meter in British English:', en_GB('meter'))

if __name__ == '__main__':
    with Podb('po.db') as po_db:
        main(po_db)
