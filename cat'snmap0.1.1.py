#!/usr/bin/env python3
"""Cat's Nmap 1.x — Tkinter GUI frontend for the real nmap binary.
Scan only systems you own or have permission to assess.

Ships with a pre-bundled nmap under vendor/nmap/ (preferred). Falls back to a
system nmap on PATH, or offers to install via Homebrew if nothing is found.
"""
import os
import queue
import shlex
import sys
import shutil
import signal
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_DIR = os.path.dirname(os.path.abspath(__file__))
# PyInstaller one-file applications extract packaged resources into _MEIPASS.
RESOURCE_DIR = getattr(sys, '_MEIPASS', APP_DIR)
BUNDLED_NMAP = os.path.join(RESOURCE_DIR, 'vendor', 'nmap', 'bin', 'nmap')
BUNDLED_DATADIR = os.path.join(RESOURCE_DIR, 'vendor', 'nmap', 'share', 'nmap')
BUNDLED_LIBDIR = os.path.join(RESOURCE_DIR, 'vendor', 'nmap', 'lib')


def resolve_nmap():
    """Return (nmap_path, datadir_or_None, using_bundle)."""
    if os.path.isfile(BUNDLED_NMAP) and os.access(BUNDLED_NMAP, os.X_OK):
        datadir = BUNDLED_DATADIR if os.path.isdir(BUNDLED_DATADIR) else None
        return BUNDLED_NMAP, datadir, True
    for candidate in (
        shutil.which('nmap'),
        '/opt/homebrew/bin/nmap',
        '/usr/local/bin/nmap',
        '/usr/bin/nmap',
    ):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate, None, False
    return '', None, False


# These are the principal Nmap runtime databases. Nmap can use additional
# optional data files depending on its build and the selected scan.
NMAP_DATA_FILES = (
    'nmap-services', 'nmap-service-probes', 'nmap-os-db',
    'nmap-protocols', 'nmap-rpc', 'nmap-mac-prefixes',
)

def _find_active_datadir(executable, bundled_datadir=None):
    """Find Nmap's data files without assuming the optional vendor folder exists."""
    candidates = [bundled_datadir] if bundled_datadir else []
    real_exe = os.path.realpath(executable)
    prefix = os.path.dirname(os.path.dirname(real_exe))
    candidates.extend([
        os.path.join(prefix, 'share', 'nmap'),
        os.path.join(os.path.dirname(os.path.dirname(executable)), 'share', 'nmap'),
        '/opt/homebrew/share/nmap', '/usr/local/share/nmap',
        '/usr/share/nmap',
    ])
    for path in dict.fromkeys(filter(None, candidates)):
        if os.path.isfile(os.path.join(path, 'nmap-services')):
            return path
    return None


def bundle_diagnostics():
    """Audit the active Nmap and separately report standalone bundle readiness."""
    executable, bundled_datadir, using_bundle = resolve_nmap()
    lines = ["Cat's Nmap — runtime and bundle audit", '=' * 42]
    bundled_ok = os.path.isfile(BUNDLED_NMAP) and os.access(BUNDLED_NMAP, os.X_OK)
    lines.append(f'Bundled executable: {"PRESENT" if bundled_ok else "NOT PACKAGED"}')
    lines.append(f'Expected bundle path: {BUNDLED_NMAP}')
    if not executable:
        lines.append('Active Nmap: NOT FOUND')
        lines.append('Install Nmap using Homebrew or package a complete vendor/nmap directory.')
        return '\n'.join(lines)
    lines.append(f'Active Nmap: {executable}')
    lines.append(f'Mode: {"BUNDLED" if using_bundle else "SYSTEM INSTALLATION (not standalone)"}')
    datadir = _find_active_datadir(executable, bundled_datadir)
    lines.append(f'Active data directory: {datadir or "NOT FOUND"}')
    for name in dict.fromkeys(NMAP_DATA_FILES):
        found = bool(datadir and os.path.isfile(os.path.join(datadir, name)))
        lines.append(f'  {name}: {"OK" if found else "MISSING"}')
    scripts_dir = os.path.join(datadir, 'scripts') if datadir else ''
    scripts = [name for name in os.listdir(scripts_dir) if name.endswith('.nse')] if os.path.isdir(scripts_dir) else []
    lines.append(f'NSE scripts: {len(scripts)} found')
    lines.append(f'Script database: {"OK" if scripts_dir and os.path.isfile(os.path.join(scripts_dir, "script.db")) else "MISSING"}')
    if using_bundle:
        lines.append(f'Bundled library directory: {"PRESENT" if os.path.isdir(BUNDLED_LIBDIR) else "ABSENT (may not be required)"}')
    try:
        result = subprocess.run([executable, '--version'], env=nmap_run_env(using_bundle),
                                capture_output=True, text=True, timeout=8, check=False)
        lines.append(f'Executable version test: {"PASS" if result.returncode == 0 else "FAIL"} (exit {result.returncode})')
        lines.append((result.stdout or result.stderr).strip()[:800])
    except (OSError, subprocess.TimeoutExpired) as exc:
        lines.append(f'Executable version test: FAIL — {exc}')
    if not using_bundle:
        lines.append('RESULT: System Nmap is usable, but Nmap is NOT bundled with this .py.')
        lines.append('A standalone release needs the native binary, data, and dependencies packaged.')
    else:
        lines.append('RESULT: Bundled Nmap detected; portability still requires dependency testing.')
    lines.append('Only scan systems you own or are authorized to assess.')
    return '\n'.join(lines)


def brew_install_nmap():
    """Install nmap with Homebrew. Returns True on success."""
    brew = shutil.which('brew') or (
        '/opt/homebrew/bin/brew' if os.path.isfile('/opt/homebrew/bin/brew') else None
    )
    if not brew:
        return False
    try:
        subprocess.run([brew, 'install', 'nmap'], check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def nmap_run_env(using_bundle):
    env = os.environ.copy()
    if using_bundle and os.path.isdir(BUNDLED_LIBDIR):
        # Prefer bundled dylibs when the absolute Homebrew paths are absent.
        prev = env.get('DYLD_FALLBACK_LIBRARY_PATH', '')
        env['DYLD_FALLBACK_LIBRARY_PATH'] = (
            BUNDLED_LIBDIR + (os.pathsep + prev if prev else '')
        )
    return env

BG = '#0b1220'
PANEL = '#121a2b'
BLUE = '#3b82f6'
TEXT = '#60a5fa'
MUTED = '#93c5fd'
BLACK = '#000000'
ENTRY = {'bg': PANEL, 'fg': TEXT, 'insertbackground': TEXT, 'relief': 'flat'}
LABEL = {'bg': BG, 'fg': TEXT}
CHECK = {'bg': BG, 'fg': TEXT, 'activebackground': BG, 'activeforeground': TEXT,
         'selectcolor': PANEL, 'highlightthickness': 0}

SCAN_TYPES = [
    ('TCP Connect (-sT)', '-sT'),
    ('TCP SYN (-sS)', '-sS'),
    ('UDP (-sU)', '-sU'),
    ('TCP ACK (-sA)', '-sA'),
    ('TCP Window (-sW)', '-sW'),
    ('TCP Maimon (-sM)', '-sM'),
    ('TCP Null (-sN)', '-sN'),
    ('TCP FIN (-sF)', '-sF'),
    ('TCP Xmas (-sX)', '-sX'),
    ('SCTP INIT (-sY)', '-sY'),
    ('SCTP COOKIE-ECHO (-sZ)', '-sZ'),
    ('IP Protocol (-sO)', '-sO'),
    ('List scan (-sL)', '-sL'),
    ('Ping sweep (-sn)', '-sn'),
    ('No port scan (-sn)', '-sn'),
]

PORT_PRESETS = [
    ('Default (nmap top 1000)', ''),
    ('Fast (-F)', '-F'),
    ('Top 100', '--top-ports 100'),
    ('Top 1000', '--top-ports 1000'),
    ('All ports (-p-)', '-p-'),
    ('Common services', '-p 21,22,23,25,53,80,110,139,143,443,445,587,993,995,3306,3389,5432,5900,6379,8080,8443'),
    ('Web', '-p 80,443,8080,8443,8000,8888,3000'),
    ('Custom…', 'custom'),
]

TIMING = [f'T{i} — {n}' for i, n in enumerate(
    ('Paranoid', 'Sneaky', 'Polite', 'Normal', 'Aggressive', 'Insane'))]

SCRIPT_PRESETS = [
    '',
    'default',
    'safe',
    'auth',
    'broadcast',
    'brute',
    'discovery',
    'dos',
    'exploit',
    'external',
    'fuzzer',
    'intrusive',
    'malware',
    'safe,discovery',
    'vuln',
    'version',
]


class CatsNmap(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cat's Nmap 1.x")
        self.configure(bg=BG)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.running = False
        self.proc = None
        self.nmap_path, self.nmap_datadir, self.nmap_bundled = resolve_nmap()
        # Withdraw until size is set — avoids macOS Tk opening as a square default.
        self.withdraw()
        self._style()
        self._build()
        self._place_centered(1920, 1080)
        self.deiconify()
        self.after(80, self._poll)
        self._refresh_cmd()
        if not self.nmap_path:
            self.after(200, self._offer_install_nmap)

    def _style(self):
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.configure('TNotebook.Tab', background=PANEL, foreground=TEXT, padding=(12, 6))
        style.map('TNotebook.Tab', background=[('selected', BLUE)], foreground=[('selected', '#fff')])
        style.configure('Blue.Horizontal.TProgressbar', troughcolor=PANEL, background=BLUE, bordercolor=PANEL)
        style.configure('Dark.TCombobox', fieldbackground=PANEL, background=PANEL, foreground=TEXT)

    def _place_centered(self, w, h):
        """Open as a 16:9 1920×1080 window centered on screen (no maxsize lock)."""
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.resizable(True, True)
        self.minsize(960, 540)
        # Size first, then position — more reliable than one combined geometry on macOS Tk.
        self.geometry(f'{w}x{h}')
        self.update_idletasks()
        self.geometry(f'+{x}+{y}')

    def _label(self, parent, text, **kw):
        opts = {**LABEL, **kw}
        return tk.Label(parent, text=text, **opts)

    def _entry(self, parent, var=None, width=28, **kw):
        e = tk.Entry(parent, textvariable=var, width=width, **ENTRY, **kw)
        return e

    def _check(self, parent, text, var):
        return tk.Checkbutton(parent, text=text, variable=var, **CHECK)

    def _button(self, parent, text, command):
        return tk.Button(parent, text=text, command=command, bg=BLACK, fg=TEXT,
                         activebackground=PANEL, activeforeground=TEXT,
                         relief='flat', padx=12, pady=6)

    def _section(self, parent, title):
        f = tk.LabelFrame(parent, text=title, bg=BG, fg=MUTED, padx=10, pady=8,
                          labelanchor='nw', highlightthickness=0)
        f.pack(fill='x', padx=8, pady=6)
        return f

    def _build(self):
        top = tk.Frame(self, bg=BG)
        top.pack(fill='x', padx=16, pady=(12, 4))
        self._label(top, "CAT'S NMAP 1.X", font=('Arial', 22, 'bold')).pack(side='left')
        if self.nmap_path and self.nmap_bundled:
            nmap_info = f'nmap: bundled ({self.nmap_path})'
        elif self.nmap_path:
            nmap_info = f'nmap: {self.nmap_path}'
        else:
            nmap_info = 'nmap: NOT FOUND — bundled vendor/ missing; install via Homebrew'
        self.nmap_info_var = tk.StringVar(value=nmap_info)
        self._label(top, '', textvariable=self.nmap_info_var,
                    fg=MUTED if self.nmap_path else '#f87171',
                    font=('Menlo', 11)).pack(side='right')

        body = tk.Frame(self, bg=BG)
        body.pack(fill='both', expand=True, padx=12, pady=4)
        body.columnconfigure(0, weight=2, minsize=520)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        left_wrap = tk.Frame(body, bg=BG)
        left_wrap.grid(row=0, column=0, sticky='nsew', padx=(0, 8))
        canvas = tk.Canvas(left_wrap, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(left_wrap, orient='vertical', command=canvas.yview)
        left = tk.Frame(canvas, bg=BG)
        left.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=left, anchor='nw')
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(1, width=e.width))

        # --- Target ---
        sec = self._section(left, 'Target')
        self.target = tk.StringVar(value='127.0.0.1')
        self._label(sec, 'Hosts / CIDR / ranges (space-separated):').pack(anchor='w')
        self._entry(sec, self.target, width=56).pack(fill='x', pady=2)
        row = tk.Frame(sec, bg=BG)
        row.pack(fill='x', pady=2)
        self.iL = tk.StringVar()
        self.exclude = tk.StringVar()
        self._label(row, '-iL file:').pack(side='left')
        self._entry(row, self.iL, width=18).pack(side='left', padx=4)
        self._button(row, '…', lambda: self._pick_file(self.iL)).pack(side='left')
        self._label(row, '--exclude:').pack(side='left', padx=(10, 0))
        self._entry(row, self.exclude, width=18).pack(side='left', padx=4)
        row2 = tk.Frame(sec, bg=BG)
        row2.pack(fill='x', pady=2)
        self.ipv6 = tk.BooleanVar()
        self.random_targets = tk.StringVar()
        self._check(row2, '-6 IPv6', self.ipv6).pack(side='left')
        self._label(row2, '-iR count:').pack(side='left', padx=(12, 0))
        self._entry(row2, self.random_targets, width=8).pack(side='left', padx=4)

        # --- Scan technique ---
        sec = self._section(left, 'Scan technique')
        self.scan_type = tk.StringVar(value=SCAN_TYPES[0][0])
        ttk.Combobox(sec, textvariable=self.scan_type, values=[s[0] for s in SCAN_TYPES],
                     state='readonly', width=36).pack(anchor='w', pady=2)
        opts = tk.Frame(sec, bg=BG)
        opts.pack(fill='x')
        self.pn = tk.BooleanVar()
        self.n_dns = tk.BooleanVar()
        self.r_order = tk.BooleanVar()
        self.traceroute = tk.BooleanVar()
        self.reason = tk.BooleanVar()
        self.open_only = tk.BooleanVar()
        for text, var in (('-Pn', self.pn), ('-n no DNS', self.n_dns),
                          ('-r ordered', self.r_order), ('--traceroute', self.traceroute),
                          ('--reason', self.reason), ('--open', self.open_only)):
            self._check(opts, text, var).pack(side='left', padx=(0, 10))

        # --- Ports ---
        sec = self._section(left, 'Ports')
        self.port_preset = tk.StringVar(value=PORT_PRESETS[0][0])
        self.custom_ports = tk.StringVar()
        ttk.Combobox(sec, textvariable=self.port_preset, values=[p[0] for p in PORT_PRESETS],
                     state='readonly', width=40).pack(anchor='w', pady=2)
        pr = tk.Frame(sec, bg=BG)
        pr.pack(fill='x')
        self._label(pr, 'Custom -p / --top-ports:').pack(side='left')
        self._entry(pr, self.custom_ports, width=40).pack(side='left', padx=6, fill='x', expand=True)

        # --- Discovery ---
        sec = self._section(left, 'Host discovery')
        disc = tk.Frame(sec, bg=BG)
        disc.pack(fill='x')
        self.PE = tk.BooleanVar(value=True)
        self.PP = tk.BooleanVar()
        self.PM = tk.BooleanVar()
        self.PS = tk.StringVar()
        self.PA = tk.StringVar()
        self.PU = tk.StringVar()
        self.PY = tk.StringVar()
        for text, var in (('ICMP echo (-PE)', self.PE), ('timestamp (-PP)', self.PP),
                          ('netmask (-PM)', self.PM)):
            self._check(disc, text, var).pack(anchor='w')
        for label, var in (('-PS ports', self.PS), ('-PA ports', self.PA),
                           ('-PU ports', self.PU), ('-PY ports', self.PY)):
            r = tk.Frame(sec, bg=BG)
            r.pack(fill='x', pady=1)
            self._label(r, label, width=12, anchor='w').pack(side='left')
            self._entry(r, var, width=28).pack(side='left')

        # --- Service / OS / Scripts ---
        sec = self._section(left, 'Service, OS & scripts')
        so = tk.Frame(sec, bg=BG)
        so.pack(fill='x')
        self.sV = tk.BooleanVar()
        self.O = tk.BooleanVar()
        self.A = tk.BooleanVar()
        self.sC = tk.BooleanVar()
        for text, var in (('-sV version', self.sV), ('-O OS detect', self.O),
                          ('-A aggressive', self.A), ('-sC default scripts', self.sC)):
            self._check(so, text, var).pack(side='left', padx=(0, 12))
        r = tk.Frame(sec, bg=BG)
        r.pack(fill='x', pady=2)
        self.version_intensity = tk.StringVar()
        self._label(r, '--version-intensity (0-9):').pack(side='left')
        self._entry(r, self.version_intensity, width=4).pack(side='left', padx=4)
        self.osscan_guess = tk.BooleanVar()
        self.fuzzy = tk.BooleanVar()
        self._check(r, '--osscan-guess', self.osscan_guess).pack(side='left', padx=8)
        self._check(r, '--fuzzy', self.fuzzy).pack(side='left')
        r = tk.Frame(sec, bg=BG)
        r.pack(fill='x', pady=2)
        self.script = tk.StringVar()
        self._label(r, '--script:').pack(side='left')
        ttk.Combobox(r, textvariable=self.script, values=SCRIPT_PRESETS, width=28).pack(side='left', padx=4)
        self.script_args = tk.StringVar()
        self._label(r, '--script-args:').pack(side='left', padx=(8, 0))
        self._entry(r, self.script_args, width=24).pack(side='left', padx=4)

        # --- Timing & performance ---
        sec = self._section(left, 'Timing & performance')
        r = tk.Frame(sec, bg=BG)
        r.pack(fill='x')
        self.timing = tk.StringVar(value=TIMING[3])
        self._label(r, 'Timing (-T):').pack(side='left')
        ttk.Combobox(r, textvariable=self.timing, values=TIMING, state='readonly',
                     width=22).pack(side='left', padx=4)
        perf = tk.Frame(sec, bg=BG)
        perf.pack(fill='x', pady=4)
        self.min_rate = tk.StringVar()
        self.max_rate = tk.StringVar()
        self.min_parallel = tk.StringVar()
        self.max_parallel = tk.StringVar()
        self.host_timeout = tk.StringVar()
        self.max_retries = tk.StringVar()
        for label, var in (('--min-rate', self.min_rate), ('--max-rate', self.max_rate),
                           ('--min-parallelism', self.min_parallel),
                           ('--max-parallelism', self.max_parallel),
                           ('--host-timeout', self.host_timeout),
                           ('--max-retries', self.max_retries)):
            cell = tk.Frame(perf, bg=BG)
            cell.pack(side='left', padx=(0, 10))
            self._label(cell, label).pack(anchor='w')
            self._entry(cell, var, width=10).pack()

        # --- Evasion ---
        sec = self._section(left, 'Firewall / IDS evasion')
        ev = tk.Frame(sec, bg=BG)
        ev.pack(fill='x')
        self.f_frag = tk.BooleanVar()
        self.D = tk.StringVar()
        self.S = tk.StringVar()
        self.g = tk.StringVar()
        self.data_length = tk.StringVar()
        self.ttl = tk.StringVar()
        self.spoof_mac = tk.StringVar()
        self.badsum = tk.BooleanVar()
        self._check(ev, '-f fragment', self.f_frag).pack(side='left')
        self._check(ev, '--badsum', self.badsum).pack(side='left', padx=8)
        for label, var, w in (('-D decoys', self.D, 16), ('-S spoof IP', self.S, 14),
                              ('-g source port', self.g, 8), ('--data-length', self.data_length, 6),
                              ('--ttl', self.ttl, 4), ('--spoof-mac', self.spoof_mac, 12)):
            cell = tk.Frame(sec, bg=BG)
            cell.pack(side='left', padx=(0, 8), pady=2)
            self._label(cell, label).pack(anchor='w')
            self._entry(cell, var, width=w).pack()

        # --- Output options ---
        sec = self._section(left, 'Output & verbosity')
        out = tk.Frame(sec, bg=BG)
        out.pack(fill='x')
        self.v = tk.BooleanVar(value=True)
        self.vv = tk.BooleanVar()
        self.d = tk.BooleanVar()
        self.packet_trace = tk.BooleanVar()
        for text, var in (('-v', self.v), ('-vv', self.vv), ('-d', self.d),
                          ('--packet-trace', self.packet_trace)):
            self._check(out, text, var).pack(side='left', padx=(0, 10))
        r = tk.Frame(sec, bg=BG)
        r.pack(fill='x', pady=4)
        self.oN = tk.StringVar()
        self.oX = tk.StringVar()
        self.oG = tk.StringVar()
        self.oA = tk.StringVar()
        for label, var in (('-oN', self.oN), ('-oX', self.oX), ('-oG', self.oG), ('-oA', self.oA)):
            cell = tk.Frame(r, bg=BG)
            cell.pack(side='left', padx=(0, 8))
            self._label(cell, label).pack(side='left')
            self._entry(cell, var, width=12).pack(side='left', padx=2)
            self._button(cell, '…', lambda v=var: self._pick_save(v)).pack(side='left')

        # --- Extra args ---
        sec = self._section(left, 'Extra raw arguments')
        self.extra = tk.StringVar()
        self._entry(sec, self.extra, width=56).pack(fill='x')
        self._label(sec, 'Appended as-is to the nmap command (advanced).',
                    fg=MUTED, font=('Arial', 10)).pack(anchor='w')

        for var in (self.target, self.iL, self.exclude, self.random_targets, self.scan_type,
                    self.port_preset, self.custom_ports, self.script, self.script_args,
                    self.timing, self.extra, self.version_intensity, self.PS, self.PA,
                    self.PU, self.PY, self.min_rate, self.max_rate, self.min_parallel,
                    self.max_parallel, self.host_timeout, self.max_retries, self.D, self.S,
                    self.g, self.data_length, self.ttl, self.spoof_mac, self.oN, self.oX,
                    self.oG, self.oA):
            var.trace_add('write', lambda *_: self._refresh_cmd())
        for var in (self.ipv6, self.pn, self.n_dns, self.r_order, self.traceroute, self.reason,
                    self.open_only, self.PE, self.PP, self.PM, self.sV, self.O, self.A, self.sC,
                    self.osscan_guess, self.fuzzy, self.f_frag, self.badsum, self.v, self.vv,
                    self.d, self.packet_trace):
            var.trace_add('write', lambda *_: self._refresh_cmd())

        # --- Right: command + output ---
        right = tk.Frame(body, bg=BG)
        right.grid(row=0, column=1, sticky='nsew')
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)

        cmd_frame = tk.Frame(right, bg=BG)
        cmd_frame.grid(row=0, column=0, sticky='ew')
        self._label(cmd_frame, 'Command preview', font=('Arial', 12, 'bold')).pack(anchor='w')
        self.cmd_view = tk.Text(cmd_frame, height=3, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                                font=('Menlo', 11), wrap='word', borderwidth=0, padx=8, pady=6)
        self.cmd_view.pack(fill='x', pady=4)

        btns = tk.Frame(right, bg=BG)
        btns.grid(row=1, column=0, sticky='ew', pady=6)
        self.start_btn = self._button(btns, 'SCAN', self.start)
        self.start_btn.pack(side='left', padx=(0, 6))
        self._button(btns, 'STOP', self.stop).pack(side='left', padx=6)
        self._button(btns, 'SAVE OUTPUT', self.save).pack(side='left', padx=6)
        self._button(btns, 'COPY CMD', self.copy_cmd).pack(side='left', padx=6)
        self._button(btns, 'CLEAR', self.clear_out).pack(side='left', padx=6)
        self._button(btns, 'AUDIT BUNDLE', self.audit_bundle).pack(side='left', padx=6)
        self.status = tk.StringVar(value='Ready — scan authorized hosts only')
        self._label(btns, '', textvariable=self.status, fg=MUTED).pack(side='left', padx=16)

        self.progress = ttk.Progressbar(right, mode='indeterminate',
                                        style='Blue.Horizontal.TProgressbar')
        self.progress.grid(row=1, column=0, sticky='e', padx=4)

        out_frame = tk.Frame(right, bg=PANEL)
        out_frame.grid(row=2, column=0, sticky='nsew', pady=(4, 8))
        out_frame.rowconfigure(0, weight=1)
        out_frame.columnconfigure(0, weight=1)
        self.output = tk.Text(out_frame, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                              selectbackground=BLUE, font=('Menlo', 11),
                              wrap='none', borderwidth=0, padx=10, pady=8)
        yscroll = tk.Scrollbar(out_frame, command=self.output.yview)
        xscroll = tk.Scrollbar(out_frame, orient='horizontal', command=self.output.xview)
        self.output.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.output.grid(row=0, column=0, sticky='nsew')
        yscroll.grid(row=0, column=1, sticky='ns')
        xscroll.grid(row=1, column=0, sticky='ew')
        banner = ("Cat's Nmap 1.x — full nmap frontend\n"
                  "Uses the pre-bundled nmap in vendor/nmap/ (or system nmap) for all scan types,\n"
                  "scripts, and OS/service detection.\n"
                  "Only scan systems you own or have explicit permission to assess.\n\n")
        self._write(banner)
        if self.nmap_bundled:
            self._write(f'Using bundled nmap: {self.nmap_path}\n'
                        f'Datadir: {self.nmap_datadir}\n\n')
        elif self.nmap_path:
            self._write(f'Using system nmap: {self.nmap_path}\n\n')
        else:
            self._write('ERROR: no bundled or system nmap found.\n'
                        'Expected vendor/nmap/bin/nmap next to this script, or: brew install nmap\n')

    def _pick_file(self, var):
        path = filedialog.askopenfilename(title='Select target list')
        if path:
            var.set(path)

    def _pick_save(self, var):
        path = filedialog.asksaveasfilename(title='Output file')
        if path:
            var.set(path)

    def _write(self, msg):
        self.output.insert('end', msg)
        self.output.see('end')

    def audit_bundle(self):
        self._write('\n' + bundle_diagnostics() + '\n')

    def clear_out(self):
        self.output.delete('1.0', 'end')

    def copy_cmd(self):
        cmd = self.cmd_view.get('1.0', 'end-1c')
        self.clipboard_clear()
        self.clipboard_append(cmd)
        self.status.set('Command copied')

    def _flag_for_scan(self):
        label = self.scan_type.get()
        for name, flag in SCAN_TYPES:
            if name == label:
                return flag
        return '-sT'

    def _port_args(self):
        preset = self.port_preset.get()
        for name, val in PORT_PRESETS:
            if name == preset:
                if val == 'custom' or name.startswith('Custom'):
                    raw = self.custom_ports.get().strip()
                    if not raw:
                        return []
                    if raw.startswith('-'):
                        return raw.split()
                    return ['-p', raw]
                if not val:
                    custom = self.custom_ports.get().strip()
                    if custom:
                        if custom.startswith('-'):
                            return custom.split()
                        return ['-p', custom]
                    return []
                return val.split()
        return []

    def _offer_install_nmap(self):
        if self.nmap_path:
            return
        if not messagebox.askyesno(
                'nmap missing',
                'No bundled or system nmap was found.\n\n'
                'Install nmap with Homebrew now?'):
            return
        self.status.set('Installing nmap via Homebrew...')
        self._write('\nRunning: brew install nmap\n')

        def work():
            ok = brew_install_nmap()
            self.events.put(('nmap_install', ok))

        threading.Thread(target=work, daemon=True).start()

    def _reload_nmap(self):
        self.nmap_path, self.nmap_datadir, self.nmap_bundled = resolve_nmap()
        if self.nmap_path and self.nmap_bundled:
            info = f'nmap: bundled ({self.nmap_path})'
        elif self.nmap_path:
            info = f'nmap: {self.nmap_path}'
        else:
            info = 'nmap: NOT FOUND'
        self.nmap_info_var.set(info)
        self._refresh_cmd()

    def build_command(self):
        if not self.nmap_path:
            raise ValueError('nmap binary not found (bundled vendor/ or PATH)')
        cmd = [self.nmap_path]
        if self.nmap_datadir:
            cmd.extend(['--datadir', self.nmap_datadir])
        if self.ipv6.get():
            cmd.append('-6')
        flag = self._flag_for_scan()
        # Avoid duplicating -sn if chosen twice in list
        if flag:
            cmd.append(flag)
        cmd.extend(self._port_args())
        if self.pn.get():
            cmd.append('-Pn')
        if self.n_dns.get():
            cmd.append('-n')
        if self.r_order.get():
            cmd.append('-r')
        if self.traceroute.get():
            cmd.append('--traceroute')
        if self.reason.get():
            cmd.append('--reason')
        if self.open_only.get():
            cmd.append('--open')
        # Discovery (skip when -Pn or -sn/-sL alone dominates — still allow explicit)
        if not self.pn.get():
            if self.PE.get():
                cmd.append('-PE')
            if self.PP.get():
                cmd.append('-PP')
            if self.PM.get():
                cmd.append('-PM')
            for opt, var in (('-PS', self.PS), ('-PA', self.PA), ('-PU', self.PU), ('-PY', self.PY)):
                val = var.get().strip()
                if val:
                    cmd.append(f'{opt}{val}')
        if self.A.get():
            cmd.append('-A')
        else:
            if self.sV.get():
                cmd.append('-sV')
            if self.O.get():
                cmd.append('-O')
            if self.sC.get():
                cmd.append('-sC')
        vi = self.version_intensity.get().strip()
        if vi:
            cmd.extend(['--version-intensity', vi])
        if self.osscan_guess.get():
            cmd.append('--osscan-guess')
        if self.fuzzy.get():
            cmd.append('--fuzzy')
        script = self.script.get().strip()
        if script:
            cmd.extend(['--script', script])
        sargs = self.script_args.get().strip()
        if sargs:
            cmd.extend(['--script-args', sargs])
        t = self.timing.get()
        if t:
            cmd.append(f'-T{t[1]}')  # 'T3 — Normal' -> -T3
        for opt, var in (('--min-rate', self.min_rate), ('--max-rate', self.max_rate),
                         ('--min-parallelism', self.min_parallel),
                         ('--max-parallelism', self.max_parallel),
                         ('--host-timeout', self.host_timeout),
                         ('--max-retries', self.max_retries)):
            val = var.get().strip()
            if val:
                cmd.extend([opt, val])
        if self.f_frag.get():
            cmd.append('-f')
        if self.badsum.get():
            cmd.append('--badsum')
        for opt, var in (('-D', self.D), ('-S', self.S), ('-g', self.g),
                         ('--data-length', self.data_length), ('--ttl', self.ttl),
                         ('--spoof-mac', self.spoof_mac)):
            val = var.get().strip()
            if val:
                if opt.startswith('--'):
                    cmd.extend([opt, val])
                else:
                    cmd.extend([opt, val])
        if self.vv.get():
            cmd.append('-vv')
        elif self.v.get():
            cmd.append('-v')
        if self.d.get():
            cmd.append('-d')
        if self.packet_trace.get():
            cmd.append('--packet-trace')
        for opt, var in (('-oN', self.oN), ('-oX', self.oX), ('-oG', self.oG), ('-oA', self.oA)):
            val = var.get().strip()
            if val:
                cmd.extend([opt, val])
        if self.iL.get().strip():
            cmd.extend(['-iL', self.iL.get().strip()])
        if self.exclude.get().strip():
            cmd.extend(['--exclude', self.exclude.get().strip()])
        if self.random_targets.get().strip():
            cmd.extend(['-iR', self.random_targets.get().strip()])
        extra = self.extra.get().strip()
        if extra:
            cmd.extend(extra.split())
        targets = self.target.get().strip()
        if targets and not self.iL.get().strip() and not self.random_targets.get().strip():
            cmd.extend(targets.split())
        elif not targets and not self.iL.get().strip() and not self.random_targets.get().strip():
            raise ValueError('Enter a target, -iL file, or -iR count')
        return cmd

    def _refresh_cmd(self):
        try:
            cmd = self.build_command()
            text = shlex.join(cmd)
        except ValueError as exc:
            text = f'# {exc}'
        self.cmd_view.configure(state='normal')
        self.cmd_view.delete('1.0', 'end')
        self.cmd_view.insert('end', text)
        self.cmd_view.configure(state='normal')

    def start(self):
        if self.running:
            return
        if not self.nmap_path:
            messagebox.showerror(
                'nmap missing',
                'Bundled nmap not found at vendor/nmap/bin/nmap.\n'
                'Install with Homebrew or restore the vendor/ folder.')
            self._offer_install_nmap()
            return
        try:
            cmd = self.build_command()
        except ValueError as exc:
            messagebox.showerror('Invalid input', str(exc))
            return
        if not messagebox.askyesno(
                'Authorization',
                'Only scan systems you own or have explicit written permission to assess.\n\n'
                'Continue with this nmap command?'):
            return
        self.cancel.clear()
        self.running = True
        self.output.delete('1.0', 'end')
        self.start_btn.configure(state='disabled')
        self.status.set('Scanning...')
        self.progress.start(12)
        self._write('$ ' + shlex.join(cmd) + '\n\n')
        threading.Thread(target=self._run_nmap, args=(cmd,), daemon=True).start()

    def _run_nmap(self, cmd):
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
                start_new_session=True,
                env=nmap_run_env(self.nmap_bundled),
            )
            assert self.proc.stdout is not None
            for line in self.proc.stdout:
                if self.cancel.is_set():
                    break
                self.events.put(('line', line))
            code = self.proc.wait(timeout=2) if not self.cancel.is_set() else None
            if self.cancel.is_set():
                self._kill_proc()
                self.events.put(('done', 'stopped'))
            else:
                self.events.put(('line', f'\n[nmap exited with code {code}]\n'))
                self.events.put(('done', code))
        except FileNotFoundError:
            self.events.put(('error', 'nmap binary not found'))
        except OSError as exc:
            self.events.put(('error', str(exc)))
        finally:
            self.proc = None

    def _kill_proc(self):
        proc = self.proc
        if not proc or proc.poll() is not None:
            return
        try:
            os_kill = getattr(__import__('os'), 'killpg', None)
            if os_kill:
                import os
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            else:
                proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if os_kill:
                    import os
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                else:
                    proc.kill()
        except (OSError, ProcessLookupError):
            pass

    def stop(self):
        if self.running:
            self.cancel.set()
            self.status.set('Stopping nmap...')
            self._kill_proc()

    def _poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'line':
                    self._write(value)
                elif kind == 'done':
                    self.running = False
                    self.start_btn.configure(state='normal')
                    self.progress.stop()
                    self.progress['value'] = 0
                    self.status.set('Stopped' if value else 'Complete')
                    self._write('\nScan stopped.\n' if value else '\nScan complete.\n')
                elif kind == 'error':
                    self.running = False
                    self.start_btn.configure(state='normal')
                    self.progress.stop()
                    self.status.set('Error')
                    self._write(f'Error: {value}\n')
                elif kind == 'nmap_install':
                    if value:
                        self._reload_nmap()
                        self.status.set('nmap installed')
                        self._write('Homebrew install finished — nmap is ready.\n')
                    else:
                        self.status.set('nmap install failed')
                        self._write('Homebrew install failed. Install from https://nmap.org\n')
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def save(self):
        path = filedialog.asksaveasfilename(title='Save scan results',
                                            defaultextension='.txt',
                                            filetypes=[('Text files', '*.txt'),
                                                       ('All files', '*.*')])
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(self.output.get('1.0', 'end-1c'))
                self.status.set(f'Saved: {path}')
            except OSError as exc:
                messagebox.showerror('Save failed', str(exc))


if __name__ == '__main__':
    CatsNmap().mainloop()
