"""HTML bodies for the few emails the app sends. Plain, table-based, no external assets, so
they render the same in every client. Text alternatives live next to the callers."""

# ruff: noqa: E501

from __future__ import annotations

from html import escape


def invitation_html(
    *, app_name: str, inviter: str, title: str, access: str, email: str, link: str, days: int
) -> str:
    return f"""<!doctype html>
<html><body style="margin:0;padding:32px;background:#f6f7f8;font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#111">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center">
<table role="presentation" width="520" cellspacing="0" cellpadding="0" style="background:#fff;border:1px solid #e6e8eb;border-radius:12px;padding:32px">
<tr><td style="font-size:13px;color:#6b7280;padding-bottom:12px">{escape(app_name)}</td></tr>
<tr><td style="font-size:20px;font-weight:600;padding-bottom:12px">{escape(inviter)} shared a note with you</td></tr>
<tr><td style="font-size:15px;line-height:1.5;color:#374151;padding-bottom:24px"><b>{escape(title)}</b><br>You can <b>{escape(access)}</b> it. This invitation was sent to {escape(email)}.</td></tr>
<tr><td style="padding-bottom:24px"><a href="{escape(link)}" style="display:inline-block;background:#111;color:#fff;text-decoration:none;font-size:14px;font-weight:600;padding:10px 18px;border-radius:8px">Open the note</a></td></tr>
<tr><td style="font-size:12px;line-height:1.5;color:#6b7280">The link expires in {days} days. If you were not expecting this, you can ignore it.<br>Or paste this into your browser: {escape(link)}</td></tr>
</table></td></tr></table></body></html>"""
