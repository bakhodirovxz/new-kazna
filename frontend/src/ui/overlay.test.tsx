import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../test/axe';
import { BottomSheet } from './BottomSheet';
import { Button } from './Button';
import { ConfirmDialog } from './ConfirmDialog';
import { Drawer } from './Drawer';
import { Modal } from './Modal';
import { Tooltip } from './Tooltip';
import { TOAST_MS, ToastProvider, useToast } from './Toast';

function ModalHarness() {
  const [open, setOpen] = useState(false);
  return (
    <div id="root">
      <Button onClick={() => setOpen(true)}>Открыть</Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Новый пользователь"
        footer={<Button onClick={() => setOpen(false)}>Создать</Button>}
      >
        <label htmlFor="n">Логин</label>
        <input id="n" />
      </Modal>
    </div>
  );
}

describe('Modal', () => {
  it('traps focus, marks the app inert and restores focus on Escape', async () => {
    const { container } = render(<ModalHarness />);
    const root = container.querySelector('#root');
    const opener = screen.getByRole('button', { name: 'Открыть' });
    await userEvent.click(opener);
    const dialog = screen.getByRole('dialog', { name: 'Новый пользователь' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(root).toHaveAttribute('inert');
    expect(document.body).toHaveClass('no-scroll');
    const close = screen.getByRole('button', { name: 'Закрыть' });
    expect(close).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByLabelText('Логин')).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole('button', { name: 'Создать' })).toHaveFocus();
    await userEvent.tab();
    expect(close).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(screen.getByRole('button', { name: 'Создать' })).toHaveFocus();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(root).not.toHaveAttribute('inert');
    expect(document.body).not.toHaveClass('no-scroll');
    expect(opener).toHaveFocus();
  });

  it('closes on backdrop mousedown but not on panel clicks', async () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Окно">
        <p>текст</p>
      </Modal>,
    );
    await userEvent.click(screen.getByText('текст'));
    expect(onClose).not.toHaveBeenCalled();
    const backdrop = screen.getByRole('dialog').parentElement as HTMLElement;
    await userEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledOnce();
  });
});

describe('Overlay layering', () => {
  it('Escape closes only the innermost layer: a visible tooltip first, then the dialog', async () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Окно">
        <Tooltip content="Подсказка">{(p) => <button {...p}>Инфо</button>}</Tooltip>
      </Modal>,
    );
    await userEvent.hover(screen.getByRole('button', { name: 'Инфо' }));
    await userEvent.keyboard('{Escape}');
    expect(onClose).not.toHaveBeenCalled();
    await userEvent.unhover(screen.getByRole('button', { name: 'Инфо' }));
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('keeps the app inert until the last of nested overlays closes', () => {
    document.body.innerHTML = '<div id="root"></div>';
    const { rerender } = render(
      <>
        <Modal open onClose={vi.fn()} title="Первое">a</Modal>
        <Modal open onClose={vi.fn()} title="Второе">b</Modal>
      </>,
    );
    const root = document.getElementById('root');
    expect(root).toHaveAttribute('inert');
    rerender(
      <>
        <Modal open={false} onClose={vi.fn()} title="Первое">a</Modal>
        <Modal open onClose={vi.fn()} title="Второе">b</Modal>
      </>,
    );
    expect(root).toHaveAttribute('inert');
    expect(document.body).toHaveClass('no-scroll');
  });
});

describe('ConfirmDialog', () => {
  it('confirms and cancels', async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Заблокировать пользователя?"
        message="Все его сеансы будут завершены."
        confirmLabel="Заблокировать"
        danger
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    expect(screen.getByRole('dialog', { name: 'Заблокировать пользователя?' })).toHaveTextContent('Все его сеансы');
    await userEvent.click(screen.getByRole('button', { name: 'Заблокировать' }));
    expect(onConfirm).toHaveBeenCalledOnce();
    await userEvent.click(screen.getByRole('button', { name: 'Отмена' }));
    expect(onCancel).toHaveBeenCalledOnce();
  });
});

describe('Drawer and BottomSheet', () => {
  it('render labelled dialogs with a close button', async () => {
    const onClose = vi.fn();
    const { rerender } = render(
      <Drawer open onClose={onClose} title="Казначейство">
        <a href="#kazna/svod">Сводка</a>
      </Drawer>,
    );
    expect(screen.getByRole('dialog', { name: 'Казначейство' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    expect(onClose).toHaveBeenCalledOnce();
    rerender(
      <BottomSheet open onClose={onClose} title="Фильтры" footer={<Button>Готово</Button>}>
        <p>фильтры</p>
      </BottomSheet>,
    );
    expect(screen.getByRole('dialog', { name: 'Фильтры' })).toHaveTextContent('фильтры');
    await expectNoAxeViolations(screen.getByRole('dialog'));
  });
});

function ToastButton() {
  const toast = useToast();
  return <Button onClick={() => toast.show('Пароль изменён', 'success')}>Показать</Button>;
}

describe('Toast', () => {
  it('announces messages in a live region and auto-dismisses', async () => {
    vi.useFakeTimers();
    try {
      render(
        <ToastProvider>
          <ToastButton />
        </ToastProvider>,
      );
      act(() => screen.getByRole('button', { name: 'Показать' }).click());
      const region = screen.getByRole('status', { name: 'Уведомления' });
      expect(region).toHaveTextContent('Пароль изменён');
      act(() => vi.advanceTimersByTime(TOAST_MS + 10));
      expect(region).not.toHaveTextContent('Пароль изменён');
    } finally {
      vi.useRealTimers();
    }
  });

  it('can be dismissed manually', async () => {
    render(
      <ToastProvider>
        <ToastButton />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Показать' }));
    await userEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    expect(screen.getByRole('status', { name: 'Уведомления' })).toBeEmptyDOMElement();
  });
});
