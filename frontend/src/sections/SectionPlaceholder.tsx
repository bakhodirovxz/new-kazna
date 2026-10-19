import { t } from '../i18n';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';

/** TZ 6/spec 7.4: bo'lim sahifalari keyingi rejalarda — hozircha «Раздел в разработке». */
export function SectionPlaceholder({ title }: { title: string }) {
  return (
    <Card>
      <EmptyState icon="clock" title={t('section.wip.title')} text={t('section.wip.text', { title })} />
    </Card>
  );
}
