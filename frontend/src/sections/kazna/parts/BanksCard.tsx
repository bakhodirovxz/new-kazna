import type { BankBalanceOut } from '../../../api/types';
import { NoData } from '../../../dash/DataState';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import { Card } from '../../../ui/Card';

export function BanksCard({ banks, date, className }: { banks: BankBalanceOut[]; date: string; className?: string }) {
  return (
    <Card className={className} title={t('kazna.banks.title')} sub={t('kazna.banks.sub', { date: formatDate(date) })}>
      {banks.length ? (
        <Rank label={t('kazna.banks.title')} items={banks.map((b) => ({ id: b.bank_name, name: b.bank_name, value: b.balance }))} />
      ) : (
        <NoData kind="source" source={t('dash.source.balances')} />
      )}
    </Card>
  );
}
