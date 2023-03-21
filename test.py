from podb import Podb

def main(po_db: Podb):
    fr = po_db.of_lang('fr')
    it = po_db.of_lang('it')

    print('hello in French', fr('hello'))
    print('hello in Italian', it('hello'))

if __name__ == '__main__':
    with Podb('po.db') as po_db:
        main(po_db)
