import type { ZakMethodOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip «Способы закупки»: сумма заключённых договоров по способам. */
export function MethodsCard({ methods, className }: { methods: ZakMethodOut[]; className?: string }) {
  const title = t('zak.methods.title');
  return (
    <Card className={className} title={title} sub={t('zak.methods.sub')}>
      <div title={formula('contracted')}>
        <Rank label={title} items={methods.filter((m) => m.contracted > 0).map((m) => ({ id: m.method, name: m.title, value: m.contracted, note: t('zak.methods.lots', { count: m.lots }) }))} />
      </div>
    </Card>
  );
}
