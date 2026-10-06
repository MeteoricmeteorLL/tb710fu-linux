#!/usr/bin/env python3
f = '/home/meteor/u-boot-13r/lib/initcall.c'
s = open(f).read()

anchor = '''int initcall_run_list(const init_fnc_t init_sequence[])
{'''
helper = '''/*
 * TB710FU bring-up: progress markers into no-map RAM (lost_reg_mem
 * 0x9b09c000, reserved by the stock kernel and untouched by it).
 * Each entry is "<idx>:<func>\n". Read back from stock Android with
 * dd if=/dev/mem to find the initcall the boot hangs on.
 */
#define TB_PROG_BASE	0x9b09c000UL

static void tb_put_hex(char **p, ulong v, int nd)
{
	const char h[] = "0123456789abcdef";
	int i;

	for (i = nd - 1; i >= 0; i--)
		*(*p)++ = h[(v >> (i * 4)) & 0xf];
}

static void tb_progress(init_fnc_t func)
{
	static char *p = (char *)TB_PROG_BASE;
	static ulong idx;
	char buf[24];
	char *q = buf;
	int i;

	tb_put_hex(&q, idx++, 2);
	*q++ = ':';
	tb_put_hex(&q, (ulong)func, 8);
	*q++ = '\\n';
	for (i = 0; i < (q - buf); i++)
		*p++ = buf[i];
	*p = 0;
}

int initcall_run_list(const init_fnc_t init_sequence[])
{'''
assert anchor in s, 'initcall_run_list anchor not found'
s = s.replace(anchor, helper, 1)

call_anchor = '''		ret = type ? event_notify_null(type) : func();'''
call_new = '''		tb_progress(func);
		ret = type ? event_notify_null(type) : func();'''
assert call_anchor in s, 'call anchor not found'
s = s.replace(call_anchor, call_new, 1)

open(f, 'w').write(s)
print('initcall progress markers installed (0x9b09c000)')