import { t } from '../i18n';
import { plural } from '../i18n/format';
import { Icon, type IconName } from '../ui/icons';

export interface NavItem {
  id: string;
  label: string;
  icon: IconName;
  href: string;
  count?: number;
}

export interface SideModel {
  title: string;
  desc: string;
  icon: IconName;
  items: NavItem[];
  activeId: string | null;
}

export function SideMenu({ model, id, hidden, onNavigate }: { model: SideModel; id?: string; hidden?: boolean; onNavigate?(): void }) {
  return (
    <aside id={id} className="side" aria-label={model.title} hidden={hidden}>
      <div className="side-h">
        <span className="ic">
          <Icon name={model.icon} />
        </span>
        <div>
          <b>{model.title}</b>
          {model.desc ? <span>{model.desc}</span> : null}
        </div>
      </div>
      <ul className="pages">
        {model.items.map((item) => (
          <li key={item.id}>
            <a href={item.href} aria-current={item.id === model.activeId ? 'page' : undefined} onClick={onNavigate}>
              <Icon name={item.icon} />
              <span className="pages__label">{item.label}</span>
              {item.count ? (
                <span className="cnt">
                  {item.count}
                  <span className="visually-hidden"> {plural(item.count, [t('shell.attentionOne'), t('shell.attentionFew'), t('shell.attentionMany')])}</span>
                </span>
              ) : null}
            </a>
          </li>
        ))}
      </ul>
    </aside>
  );
}
