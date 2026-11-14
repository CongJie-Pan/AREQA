import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ReplyTimestamp } from '@/components/MessageList/ReplyTimestamp';

describe('ReplyTimestamp', () => {
  it.each([
    ['2026-11-14T13:59:45Z', '剛剛'],
    ['2026-11-14T13:55:00Z', '5 分鐘前'],
    ['2026-11-14T11:00:00Z', '3 小時前'],
    ['2026-11-12T14:00:00Z', '2 天前'],
    ['2026-11-07T14:00:00Z', '11月7日'],
  ])('shows the expected localized timestamp for %s', (date, label) => {
    const clock = vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-11-14T14:00:00Z'));
    try {
      const view = render(<ReplyTimestamp value={date} language="zh-TW" />);
      expect(screen.getByText(label).tagName).toBe('TIME');
      view.unmount();
    } finally {
      clock.mockRestore();
    }
  });

  it('exposes the exact Taipei date and time on keyboard focus', async () => {
    render(<ReplyTimestamp value="2026-04-10T08:21:00" language="en" />);
    const time = screen.getByText('Apr 10');
    expect(time).toHaveAttribute('dateTime', '2026-04-10T08:21:00.000Z');
    fireEvent.focus(time);
    expect(await screen.findByRole('tooltip')).toHaveTextContent(/April 10, 2026.*4:21 PM/);
  });
});
