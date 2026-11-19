"""Actual entrypoint/TTY acceptance and private Backup management contracts."""
import itertools
import json
import os
from pathlib import Path
import pty
import re
import select
import sqlite3
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def tty_run(script, answers, timeout=8, env=None):
    master, slave = pty.openpty()
    process = subprocess.Popen(['bash', str(script)], stdin=slave, stdout=slave, stderr=slave,
                               env={k:v for k,v in {**os.environ, 'TERM':'dumb', 'NO_COLOR':'1', **(env or {})}.items() if v is not None})
    os.close(slave)
    output = bytearray()
    os.write(master, answers)
    deadline = time.monotonic()+timeout
    try:
        while time.monotonic()<deadline:
            if select.select([master],[],[],.1)[0]:
                try: chunk=os.read(master,65536)
                except OSError: break
                if not chunk: break
                output.extend(chunk)
            if process.poll() is not None: break
        process.wait(timeout=2)
    finally:
        if process.poll() is None: process.kill(); process.wait()
        os.close(master)
    return process.returncode, output.decode(errors='replace')


YES_RU = ('Восстановление заменит данные проекта на этом сервере: настройки nginx, панель 3x-ui с базой, сайты (/var/www/html), '
          'сертификаты проекта и /root/cert, AdGuard Home. Всё остальное в этих папках будет удалено. Сертификаты других сайтов не затрагиваются. '
          'Продолжайте только с доверенным архивом.')
YES_EN = ('Restore replaces project data on this server: the nginx configuration, the 3x-ui panel and its database, the websites (/var/www/html), '
          'project certificates and /root/cert, and AdGuard Home. Any other files in these folders will be deleted. '
          'Certificates of other sites are not touched. Trust this archive before continuing.')
YES_RU_PROMPT = 'Для восстановления введите YES:'
YES_EN_PROMPT = 'Type YES to restore:'
FRAME = '=' * 60
PROJECT_FRAME_START = f'{FRAME}\n                     3X-UI AUTO NGINX\n'
AUTHOR_CREDIT = '© xPROMSx · github.com/xPROMSx/3x-ui-auto-nginx'


class Manager(unittest.TestCase):
    def test_server_details_requires_root_in_both_languages(self):
        for language, expected in (('1', 'Root required'), ('2', 'Нужен root')):
            with self.subTest(language=language):
                code, text = tty_run(ROOT/'x-ui-latest.sh', (language+'\n6\n0\n').encode())
                self.assertEqual(code, 0)
                self.assertIn(expected, text)
                self.assertNotIn('https://', text)

    def test_import_has_no_effects_and_preserves_traps(self):
        import re
        pattern=r'^acquire_stack_lock\(\) \{.*?^\}'
        self.assertEqual(re.search(pattern,(ROOT/'x-ui-latest.sh').read_text(),re.M|re.S)[0],
                         re.search(pattern,(ROOT/'assets/backup/x-ui-backup.sh').read_text(),re.M|re.S)[0])
        result=subprocess.run(['bash','-c','trap ":" EXIT; before=$(trap -p); source "$1"; '
            '[[ $(trap -p) == "$before" && -z ${config_password:-} && -z ${IP4:-} ]]',
            'fixture',str(ROOT/'x-ui-latest.sh')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertEqual(result.stdout,'')
        self.assertNotIn(AUTHOR_CREDIT,result.stderr)

    def test_real_entrypoint_tty_exit_back_invalid_and_no_tty(self):
        for answers in (b'1\n0\n',b'1\n9\n3\n0\n0\n'):
            code,text=tty_run(ROOT/'x-ui-latest.sh',answers)
            self.assertEqual(code,0,text)
            self.assertIn('1. Installation',text)
            self.assertIn('3. Backups',text)
            self.assertIn('4. Telegram Web Proxy Manager',text)
            self.assertNotIn('\x1b',text)
            self.assertIn('2. Change Domains',text)
        result=subprocess.run(['bash',str(ROOT/'x-ui-latest.sh')],input='1\n',text=True,capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('TTY',result.stdout+result.stderr)

    def test_language_exit_invalid_and_eof_need_no_external_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);binary=root/'bin';binary.mkdir()
            binary.joinpath('bash').symlink_to('/bin/bash')
            script=root/'entry.sh'
            script.write_text('source "'+str(ROOT/'x-ui-latest.sh')+'"\n'+'''
recover_domain_operation() { printf called > "$MARKER"; return 99; }
acquire_stack_lock() { printf called > "$MARKER"; return 99; }
run_installation() { printf called > "$MARKER"; return 99; }
entrypoint
''')
            for answers,invalid in ((b'3\n',False),(b'wrong\n3\n',True),(b'\x04',False)):
                with self.subTest(answers=answers):
                    code,text=tty_run(script,answers,env={'PATH':str(binary),'MARKER':str(root/'mutated')})
                    self.assertEqual(code,0,text)
                    self.assertIn('SELECT LANGUAGE / ВЫБЕРИТЕ ЯЗЫК',text)
                    if invalid:self.assertIn('Invalid selection / Неверный выбор',text)
                    self.assertNotIn('1. Installation',text);self.assertNotIn('1. Установка',text)
                    self.assertFalse((root/'mutated').exists())
            code,text=tty_run(ROOT/'x-ui-latest.sh',b'3\n',env={'PATH':str(binary),'XUI_AUTO_REF':'invalid/ref'})
            self.assertEqual(code,0,text);self.assertNotIn('Invalid XUI_AUTO_REF',text)

    def test_bilingual_main_backup_navigation_and_single_language_choice(self):
        for language,menu,backups in (('1','1. Installation','BACKUPS'),('2','1. Установка','РЕЗЕРВНЫЕ КОПИИ')):
            code,text=tty_run(ROOT/'x-ui-latest.sh',(language+'\n9\n3\n0\n0\n').encode())
            self.assertEqual(code,0,text);self.assertIn(menu,text);self.assertIn(backups,text)
            self.assertEqual(text.count('SELECT LANGUAGE / ВЫБЕРИТЕ ЯЗЫК'),1)
            screen_text=text.replace('\r\n','\n')
            for heading in ('SELECT LANGUAGE / ВЫБЕРИТЕ ЯЗЫК','MAIN MENU' if language=='1' else 'ГЛАВНОЕ МЕНЮ'):
                self.assertIn(f'{PROJECT_FRAME_START}      {AUTHOR_CREDIT}\n{FRAME}\n\n  {heading}\n',screen_text)
            for item in (('2. Change Domains','1. Create backup','2. List backups','3. Restore backup','0. Back','0. Exit') if language=='1' else
                         ('2. Смена доменов','1. Создать резервную копию','2. Список резервных копий','3. Восстановить резервную копию','0. Назад','0. Выход')):
                self.assertIn(item,text)
        code,text=tty_run(ROOT/'x-ui-latest.sh',b'2\n1\n')
        self.assertEqual(code,1,text)
        self.assertIn('Для этой операции нужны права root',text)
        self.assertIn('FAILED (exit 1)',text)

    def test_cli_arguments_stay_english_and_bypass_language_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            script=Path(temporary)/'entry.sh'
            script.write_text('source "'+str(ROOT/'x-ui-latest.sh')+'"\n'+'''
run_installation() { printf 'CLI:%s|' "$UI_LANG"; printf '<%s>' "$@"; return 37; }
entrypoint "$@"
''')
            for args in (('-install','y'),('-version','v3.11.0'),('-unknown','value')):
                result=subprocess.run(['bash',str(script),*args],input='2\n',capture_output=True,text=True,
                                      env={**os.environ,'UI_LANG':'ru'})
                self.assertEqual(result.returncode,37,result.stderr)
                self.assertEqual(result.stdout,'CLI:en|'+''.join('<'+arg+'>' for arg in args))
                self.assertNotIn('Select language',result.stdout)

    def test_removed_uninstall_option_fails_with_message(self):
        script='source "'+str(ROOT/'x-ui-latest.sh')+'"\nparse_installation_args -uninstall y; echo "RC:$?"\n'
        result=subprocess.run(['bash','-c',script],capture_output=True,text=True)
        self.assertIn('RC:2',result.stdout)
        self.assertIn('The -uninstall option has been removed.',result.stdout+result.stderr)

    def test_russian_install_questions_defaults_and_eof(self):
        library='source "'+str(ROOT/'x-ui-latest.sh')+'"\nUI_LANG=ru\n'
        with tempfile.TemporaryDirectory() as temporary:
            script=Path(temporary)/'questions.sh'
            script.write_text(library+'''
validate_domains && select_security && select_additional_connections && select_adguard && select_client || exit $?
printf 'FLAGS:%s:%s:%s:%s:%s:%s:%s:%s:%s:%s\n' "$INSTALL_SECURITY" "$INSTALL_WS_GRPC" "$INSTALL_VISION" "$INSTALL_AWG" "$INSTALL_XHTTP_CDN" "$INSTALL_AGH" "$CREATE_CLIENT" "$domain" "$reality_domain" "$vision_domain"
''')
            code,text=tty_run(script,b'Panel.Example\nReality.Example\n\ny\ny\ny\nVision.Example\ny\ny\ny\n\n')
            self.assertEqual(code,0,text)
            for prompt in ('домен панели 3X-UI','домен VLESS REALITY','Усилить безопасность VPS? [Y/n]',
                           'Настроить дополнительные подключения? [y/N]:',
                           'Настроить устаревшие подключения VLESS WebSocket и Trojan gRPC? [y/N]:',
                           'дополнительное подключение VLESS TCP/TLS','домен VLESS TLS Vision',
                           'дополнительное подключение AmneziaWG? [y/N]','Установить и настроить AdGuard Home? [y/N]',
                           'Создать клиента в 3X-UI'):
                self.assertIn(prompt,text)
            self.assertIn('Добавить дополнительное подключение XHTTP, совместимое с CDN? [y/N]:',text)
            self.assertIn('FLAGS:y:y:y:y:y:y:y:panel.example:reality.example:vision.example',text)
            for name,variable,default in (('select_security','INSTALL_SECURITY','y'),('select_vision','INSTALL_VISION','n'),
                    ('select_amneziawg','INSTALL_AWG','n'),('select_xhttp_cdn','INSTALL_XHTTP_CDN','n'),('select_adguard','INSTALL_AGH','n'),('select_client','CREATE_CLIENT','y')):
                for answers,expected in ((b'\n',default),(b'bad\nn\n','n'),(b'\x04','n')):
                    with self.subTest(question=name,answers=answers):
                        script.write_text(library+name+'; printf "RESULT:%s\\n" "$'+variable+'"\n')
                        code,text=tty_run(script,answers)
                        self.assertEqual(code,0,text);self.assertIn('RESULT:'+expected,text)
                        if answers.startswith(b'bad'):self.assertIn('Введите y или n.',text)

    def test_russian_adguard_dot_prompt_and_eof(self):
        source = (ROOT/'x-ui-latest.sh').read_text()
        first = source.index('    select_adguard || exit 1')
        last = source.index('\n', source.index('    select_client || exit 1', first))
        prompt = 'Включить DNS-over-TLS (DoT) для ваших устройств? [y/N]:'
        client = 'Создать клиента в 3X-UI'
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary)/'questions.sh'
            script.write_text('source "'+str(ROOT/'x-ui-latest.sh')+'"\nUI_LANG=ru\nINSTALL_AGH_DOT=n\n'
                              'uname() { echo x86_64; }\n'+source[first:last]+
                              '\nprintf "\\nRESULT:%s:%s\\n" "$INSTALL_AGH_DOT" "$CREATE_CLIENT"\n')
            for answers, expected in ((b'n\ny\n', 'n:y'), (b'y\n\x04\x04', 'n:n'),
                                      (b'y\n\nn\n', 'n:n'), (b'y\nbad\nY\nn\n', 'y:n')):
                with self.subTest(answers=answers):
                    code, text = tty_run(script, answers, env={'TERM':'xterm', 'NO_COLOR':None})
                    self.assertEqual(code, 0, text)
                    self.assertIn('RESULT:'+expected, text)
                    if answers.startswith(b'n'):
                        self.assertNotIn(prompt, text)
                        continue
                    self.assertLess(text.index('Установить и настроить AdGuard Home'), text.index(prompt))
                    self.assertLess(text.index('Он открывает порт 853'), text.index(prompt))
                    self.assertLess(text.rindex(prompt), text.index(client))
                    self.assertIn('\x1b[38;5;208m', text)
                    if b'bad' in answers:
                        self.assertEqual(text.count(prompt), 2)
                        self.assertIn('Введите y или n.', text)

    def test_russian_destructive_confirmation_still_requires_exact_yes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);script=root/'confirmation.sh';marker=root/'mutated'
            script.write_text('source "'+str(ROOT/'x-ui-latest.sh')+'"\nUI_LANG=ru\n'+'''
detect_existing_installation() { EXISTING_INSTALL_CATEGORIES=('3X-UI'); }
confirm_destructive_reinstall || exit $?
printf permitted > "$MARKER"
''')
            for answer in (b'yes\n','ДА\n'.encode(),b'n\n',b'\x04',b'YES\n'):
                with self.subTest(answer=answer):
                    marker.unlink(missing_ok=True)
                    code,text=tty_run(script,answer,env={'MARKER':str(marker)})
                    self.assertEqual(code,0 if answer==b'YES\n' else 1,text)
                    self.assertEqual(marker.exists(),answer==b'YES\n')
                    for warning in ('полная переустановка, а не обновление','Обновление ОС нельзя откатить','введите YES'):
                        self.assertIn(warning,text)

    def test_russian_summary_keeps_credentials_urls_protocols_and_states(self):
        payload={'url':'https://panel.example/subscription/fixture%25id','protocols':['REALITY','XHTTP','Hysteria2','Vision']}
        script='source "'+str(ROOT/'x-ui-latest.sh')+'"\n'+'''
UI_LANG=ru
timedatectl() { printf UTC; }; ufw() { printf 'Status: active'; }
domain=panel.example; reality_domain=reality.example; panel_path=fixture; config_username=fixture-user
config_password=$FIXTURE_PASSWORD; vision_domain=vision.example; VISION_RESULT=configured
AWG_RESULT=configured; CLIENT_RESULT=configured; AGH_RESULT=installed; AGH_PATH=adg-fixture; AGH_PASSWORD=agh-fixture
BASE_OS_RESULT=configured; APT_RESULT=configured; DOT_RESULT=configured; F2BAN_RESULT=configured
show_results
[[ -z "$CLIENT_OUTPUT" && -z "$AGH_PASSWORD" && "$config_password" == "$FIXTURE_PASSWORD" ]]
'''
        password='fixture%25\\n$(literal)'
        result=subprocess.run(['bash','-c',script],capture_output=True,text=True,
                              env={**os.environ,'CLIENT_OUTPUT':json.dumps(payload),'FIXTURE_PASSWORD':password})
        self.assertEqual(result.returncode,0,result.stderr)
        for phrase in ('Результат установки','Часовой пояс','Работает','Готов','Логин: fixture-user',
                       'Подписка:','Сохраните эти учётные данные','configured','перезагрузка 04:38'):
            self.assertIn(phrase,result.stdout)
        for value in (password,payload['url'],'https://panel.example/fixture/',
                      'https://panel.example/fixture/diag','https://panel.example/adg-fixture/',
                      'https://panel.example/dns-query',' / '.join(payload['protocols'])):
            self.assertTrue(value in result.stdout,'A displayed fixture payload changed')
        self.assertEqual(result.stdout.count(password),1)
        self.assertNotIn('\\n AmneziaWG:',result.stdout)

    def test_successful_installation_ends_at_summary_without_another_menu(self):
        with tempfile.TemporaryDirectory() as temporary:
            script=Path(temporary)/'entry.sh'
            script.write_text('source "'+str(ROOT/'x-ui-latest.sh')+'"\n'+'''
recover_domain_operation() { :; }
run_installation() { printf 'CREDENTIALS_END\\n'; }
entrypoint
''')
            for language,menu in (('1','1. Installation'),('2','1. Установка')):
                code,text=tty_run(script,(language+'\n1\n0\n').encode())
                self.assertEqual(code,0,text)
                self.assertEqual(text.count(menu),1,text)
                self.assertTrue(text.rstrip().endswith('CREDENTIALS_END'),text)
                self.assertNotIn('SUCCESS',text)

    def test_domain_and_restore_completion_cancel_and_error_keep_real_exit_codes(self):
        with tempfile.TemporaryDirectory() as temporary:
            script=Path(temporary)/'entry.sh'
            script.write_text('source "'+str(ROOT/'x-ui-latest.sh')+'"\n'+'''
recover_domain_operation() { :; }
fixture_action() {
    printf 'ACTION_END\\n'
    [[ $FIXTURE_CODE == 0 ]] || return "$FIXTURE_CODE"
    [[ $FIXTURE_COMPLETE != y ]] || ui_complete
    return 0
}
change_domains_action() { fixture_action; }
backup_action() { fixture_action; }
entrypoint
''')
            for language,menu,backups in (('1','1. Installation','BACKUPS'),('2','1. Установка','РЕЗЕРВНЫЕ КОПИИ')):
                for action in ('2\n','3\n3\n'):
                    for status,complete in ((0,'y'),(0,'n'),(10,'n'),(42,'n'),(75,'n')):
                        with self.subTest(language=language,action=action,status=status,complete=complete):
                            code,text=tty_run(script,(language+'\n'+action+'0\n0\n').encode(),
                                env={'FIXTURE_CODE':str(status),'FIXTURE_COMPLETE':complete})
                            self.assertEqual(code,status,text)
                            if complete=='y':
                                self.assertTrue(text.rstrip().endswith('ACTION_END'),text)
                                self.assertEqual(text.count(menu),1,text)
                            elif status==0:
                                self.assertEqual(text.count(menu),2,text)
                                if action.startswith('3'):self.assertEqual(text.count(backups),2,text)
                            self.assertNotIn('completed',text)
                            self.assertNotIn('SUCCESS',text)

    def test_color_policy_and_ascii_sections(self):
        with tempfile.TemporaryDirectory() as temporary:
            script=Path(temporary)/'style.sh'
            script.write_text('source "'+str(ROOT/'x-ui-latest.sh')+'"\n'+'''
ui_header 'MAIN MENU'
msg_ok SUCCESS; msg_warn WARNING; msg_err ERROR; msg_inf INFO
ui_back '0. Back'
''')
            for env,colored in (({'TERM':'xterm-256color','NO_COLOR':None},True),
                                ({'TERM':'xterm','NO_COLOR':''},False),({'TERM':'dumb','NO_COLOR':None},False)):
                code,text=tty_run(script,b'',env=env)
                self.assertEqual(code,0,text)
                self.assertEqual('\x1b[' in text,colored)
                self.assertNotIn('\x1b[1;41m',text)
                if colored:
                    for color in ('32','33','31','36'):self.assertIn('\x1b[1;'+color+'m',text)
                    self.assertIn('\x1b[2m',text)
                self.assertIn('='*60,text);self.assertIn('-'*60,text)
            result=subprocess.run(['bash',str(script)],capture_output=True,text=True,
                                  env={**os.environ,'TERM':'xterm'})
            self.assertEqual(result.returncode,0,result.stderr);self.assertNotIn('\x1b',result.stdout)

    def test_backup_list_zero_one_many_sizes_utc_and_safe_filenames(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)/'backups';directory.mkdir()
            source=(ROOT/'x-ui-latest.sh').read_text()
            body=re.search(r'^backup_list\(\) \{.*?^\}',source,re.M|re.S)[0].replace('/var/backups/x-ui',str(directory))
            script='source "$1"; UI_INTERACTIVE=1; UI_LANG=$2; '+body+'; backup_list; printf "SELECTED:%s\\n" "${BACKUP_CHOICES[@]}"'
            for count in (0,1,3):
                if count:
                    name=directory/('backup-'+str(count)+'.tar.gz');name.touch()
                    with name.open('wb') as file:file.truncate(92*1024*1024+400*1024)
                    os.utime(name,(1793204903,1793204903))
                if count==3:(directory/'unsafe-\x1b[31m\n.tar.gz').touch()
                for language in ('en','ru'):
                    result=subprocess.run(['bash','-c',script,'fixture',str(ROOT/'x-ui-latest.sh'),language],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stderr)
                    visible=result.stdout.split('SELECTED:')[0]
                    self.assertNotIn('\x1b',visible)
                    self.assertIn(str(directory),visible)
                    self.assertIn(('Archives found: ' if language=='en' else 'Найдено архивов: ')+str(count),visible)
                    if count:
                        self.assertIn('92.3 MiB',visible);self.assertIn('2026-10-28 16:28 UTC',visible)
                        self.assertIn(str(directory/'backup-1.tar.gz'),result.stdout)
                    else:self.assertIn('No backups' if language=='en' else 'нет резервных копий',visible)

    def test_backup_lists_newest_first_equal_times_by_name_and_numbers_match_choice(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)/'backups';directory.mkdir()
            times={'x-ui-backup-20261001-100000-aaaaaa.tar.gz':1790000000,'copied.tar.gz':1793000000,
                   'x-ui-backup-20261101-100000-bbbbbb.tar.gz':1795000000,'x-ui-backup-20261102-100000-cccccc.tar.gz':1795000000}
            for name,stamp in times.items():
                (directory/name).write_bytes(b'fixture');os.utime(directory/name,(stamp,stamp))
            (directory/'link.tar.gz').symlink_to(directory/'copied.tar.gz')
            (directory/'broken.tar.gz').symlink_to(directory/'absent')
            (directory/'folder.tar.gz').mkdir()
            # Newest first; equal times by name descending (the name holds the UTC creation time).
            expected=['x-ui-backup-20261102-100000-cccccc.tar.gz','x-ui-backup-20261101-100000-bbbbbb.tar.gz',
                      'copied.tar.gz','x-ui-backup-20261001-100000-aaaaaa.tar.gz']
            source=(ROOT/'x-ui-latest.sh').read_text()
            # Restore takes archive [N] from the same array the list is numbered from.
            self.assertIn('archive=${BACKUP_CHOICES[10#$choice-1]}',source)
            body=re.search(r'^backup_list\(\) \{.*?^\}',source,re.M|re.S)[0].replace('/var/backups/x-ui',str(directory))
            for interactive,pattern in (('1',r'\[(\d+)\] [^\n]*\n[^\n]*\n\s+File: ([^\n]+)'),('0',r'^(\d+)\. (\S+)  ')):
                with self.subTest(interactive=interactive):
                    script='source "$1"; UI_INTERACTIVE='+interactive+'; '+body+'; backup_list; printf "SELECTED:%s\\n" "${BACKUP_CHOICES[@]}"'
                    result=subprocess.run(['bash','-c',script,'fixture',str(ROOT/'x-ui-latest.sh')],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stderr)
                    visible=result.stdout.split('SELECTED:')[0]
                    choices=[Path(line).name for line in result.stdout.splitlines() if line.startswith('SELECTED:')]
                    shown=re.findall(pattern,visible,re.M)
                    self.assertEqual(choices,expected)
                    self.assertEqual([(int(number),Path(name).name) for number,name in shown],list(enumerate(expected,1)))
            # x-ui-backup list keeps every *.tar.gz entry; entries without a file time go last, without failing.
            result=subprocess.run(['bash','-c','source "$1"; BACKUP_STORE=$2; cmd_list',
                                   'fixture',str(ROOT/'assets/backup/x-ui-backup.sh'),str(directory)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual([line.split()[0] for line in result.stdout.splitlines()],
                             expected[:2]+['link.tar.gz']+expected[2:]+['folder.tar.gz','broken.tar.gz'])

    def test_menu_frames_wrap_to_frame_width_in_c_and_utf8_locales(self):
        from test_personal_backup import TWPM_RESTORE_EN, TWPM_RESTORE_RU
        source=(ROOT/'x-ui-latest.sh').read_text()
        warning=re.search(r"^    ui_wrap '38;5;208' \"\$\(ui_text 'Restore replaces.*$",source,re.M)[0]
        with tempfile.TemporaryDirectory() as temporary:
            script=Path(temporary)/'frames.sh'
            script.write_text('source "$1"; UI_LANG=$2; ui_refuse "$3"; ui_frame;'+warning+'\nui_frame\n')
            for locale in ('C','C.UTF-8'):
                for language,refusal,yes in (('en',TWPM_RESTORE_EN,YES_EN),('ru',TWPM_RESTORE_RU,YES_RU)):
                    with self.subTest(locale=locale,language=language):
                        result=subprocess.run(['bash',str(script),str(ROOT/'x-ui-latest.sh'),language,refusal],
                                              capture_output=True,env={**os.environ,'LC_ALL':locale})
                        self.assertEqual(result.returncode,0,result.stderr)
                        text=result.stdout.decode('utf-8')
                        self.assertNotIn('\x1b',text)
                        self.assertLessEqual(max(map(len,text.splitlines())),60,text)
                        flat=' '.join(text.split())
                        self.assertIn(f'{FRAME} [FAIL] {FRAME} {refusal} {FRAME}',flat)
                        self.assertIn(f'{FRAME} {yes} {FRAME}',flat)
            # On a terminal each wrapped line is orange on its own.
            for language,refusal in (('en',TWPM_RESTORE_EN),('ru',TWPM_RESTORE_RU)):
                wrapper=Path(temporary)/('tty-'+language+'.sh')
                wrapper.write_text('bash '+str(script)+' '+str(ROOT/'x-ui-latest.sh')+' '+language+' "$REFUSAL"\n')
                code,text=tty_run(wrapper,b'',env={'TERM':'xterm','NO_COLOR':None,'LC_ALL':'C','REFUSAL':refusal})
                self.assertEqual(code,0,text)
                lines=[line for line in text.replace('\r\n','\n').split('\n') if line and line!=FRAME and '[FAIL]' not in line]
                self.assertGreater(len(lines),8)
                for line in lines:
                    self.assertTrue(line.startswith('\x1b[38;5;208m') and line.endswith('\x1b[0m'),repr(line))

    def test_restore_metadata_uses_inspect_fields_without_raw_json_or_controls(self):
        data=dict(format_version=3,created='2026-10-28T16:28:23+00:00',os_id='ubuntu',os_version='26.04',
                  arch='amd64',x_ui_version='3.11.0',xray_version='26.10.21',adguard_home=True)
        for language in ('en','ru'):
            script='source "$1"; UI_LANG=$2; backup_metadata /private/backup.tar.gz'
            result=subprocess.run(['bash','-c',script,'fixture',str(ROOT/'x-ui-latest.sh'),language],
                                  input=json.dumps(data),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            for value in ('backup.tar.gz','28.10.2026 16:28 UTC','Backup v3','ubuntu','26.04','amd64','3.11.0','26.10.21'):
                self.assertIn(value,result.stdout)
            self.assertNotIn('"format_version"',result.stdout)
            data['created']='\x1b[31m\nunsafe'
            minimal=subprocess.run(['bash','-c',script,'fixture',str(ROOT/'x-ui-latest.sh'),language],
                input=json.dumps({'format_version':3,'created':data['created']}),capture_output=True,text=True)
            self.assertEqual(minimal.returncode,0,minimal.stderr)
            self.assertNotIn('\x1b',minimal.stdout);self.assertNotIn('Xray:',minimal.stdout)
            data['created']='2026-10-28T16:28:23+00:00'

    def test_interactive_summary_sections_partial_and_final_credential_notice(self):
        script='source "$1"; UI_INTERACTIVE=1; UI_LANG=$2; '+'''
timedatectl() { printf UTC; }; ufw() { printf 'Status: active'; }
domain=panel.example; reality_domain=reality.example; panel_path=fixture
config_username=fixture-user; config_password='fixture%25\\n$(literal)'
AWG_RESULT=configured; CORE_RESULT=${CORE_FIXTURE:-configured}
show_results "$RESULT_FIXTURE"
'''
        for language in ('en','ru'):
            for status in (0,1):
                result=subprocess.run(['bash','-c',script,'fixture',str(ROOT/'x-ui-latest.sh'),language],
                    capture_output=True,text=True,env={**os.environ,'RESULT_FIXTURE':str(status),
                        'CORE_FIXTURE':'failed_unverified' if status else 'configured'})
                self.assertEqual(result.returncode,0,result.stderr)
                for title in (('COMPONENTS','PANEL ACCESS','SUBSCRIPTION AND SERVICES','OTHER INFORMATION') if language=='en' else
                              ('КОМПОНЕНТЫ','ДОСТУП К ПАНЕЛИ','ПОДПИСКА И ДОПОЛНИТЕЛЬНЫЕ СЕРВИСЫ','ПРОЧАЯ ИНФОРМАЦИЯ')):
                    self.assertIn(title,result.stdout)
                self.assertNotIn('\\n AmneziaWG:',result.stdout)
                self.assertEqual(result.stdout.count('fixture%25\\n$(literal)'),1)
                notice='Save these credentials before closing the terminal.' if language=='en' else 'Сохраните эти учётные данные перед закрытием терминала.'
                self.assertTrue(result.stdout.rstrip().endswith(notice+'\n'+'='*60),result.stdout)
                self.assertEqual('PARTIAL' in result.stdout,bool(status))
                if status:self.assertNotIn('INSTALLATION COMPLETED',result.stdout)

    def test_language_precedes_required_recovery_and_preserves_failure_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            script=Path(temporary)/'entry.sh'
            script.write_text('source "'+str(ROOT/'x-ui-latest.sh')+'"\n'+'''
recover_domain_operation() { printf 'RECOVERY_REQUIRED\n'; return "${RECOVERY_CODE:-0}"; }
run_installation() { return 42; }
entrypoint
''')
            code,text=tty_run(script,b'2\n1\n')
            self.assertEqual(code,42,text);self.assertIn('FAILED (exit 42)',text)
            self.assertIn('проверьте указанное состояние восстановления',text)
            self.assertLess(text.index('ВЫБЕРИТЕ ЯЗЫК'),text.index('RECOVERY_REQUIRED'))
            self.assertLess(text.index('RECOVERY_REQUIRED'),text.index('1. Установка'))
            code,text=tty_run(script,b'2\n1\n',env={'RECOVERY_CODE':'75'})
            self.assertEqual(code,75,text);self.assertNotIn('1. Установка',text)
            code,text=tty_run(script,b'3\n',env={'RECOVERY_CODE':'75'})
            self.assertEqual(code,0,text);self.assertNotIn('RECOVERY_REQUIRED',text)

    def test_menu_failure_status_and_mutable_source_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            script=Path(tmp)/'entry.sh'
            script.write_text('source "'+str(ROOT/'x-ui-latest.sh')+'"\nrun_installation() { return 42; }; manager_menu\n')
            code,text=tty_run(script,b'1\n')
            self.assertEqual(code,42,text);self.assertIn('FAILED (exit 42)',text);self.assertNotIn('SUCCESS',text)
            for match in (True,False):
                downloaded=Path(tmp)/'source';downloaded.write_bytes((ROOT/'x-ui-latest.sh').read_bytes() if match else b'wrong source')
                code='source "$1"; curl() { if [[ "$*" == *api.github.com* ]]; then echo \'{"sha":"'+('b'*40)+'"}\'; else command cp "$2" "${@: -1}"; fi; }; pin_project_source'
                # Give curl fixture access to its own source argument through a global.
                code=code.replace('command cp "$2"','command cp "$DOWNLOAD"')
                result=subprocess.run(['bash','-c',code,'fixture',str(ROOT/'x-ui-latest.sh')],capture_output=True,text=True,env={**os.environ,'DOWNLOAD':str(downloaded)})
                self.assertEqual(result.returncode,0 if match else 1,result.stderr)

    def test_change_domains_menu_confirmation_and_domain_pairs(self):
        cases=(('1','next.example','cover.example','YES'),
                                          ('2','deploy.example','next-cover.example','YES'),
                                          ('3','next.example','next-cover.example','YES'),
                                          ('1','next.example','cover.example','yes'))
        for language,(choice,panel,reality,answer) in itertools.product(('en','ru'),cases):
            with self.subTest(language=language,choice=choice,answer=answer),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);(root/'db').touch();stage=root/'stage';stage.mkdir()
                source=(ROOT/'x-ui-latest.sh').read_text()
                body=re.search(r'^change_domains_action\(\) \(.*?^\)',source,re.M|re.S).group().replace('/etc/x-ui/x-ui.db',str(root/'db'))
                library='source "'+str(ROOT/'x-ui-latest.sh')+'"\nUI_LANG='+language+'\n'+body+'\n'
                library+='''acquire_stack_lock() { :; }; recover_domain_operation() { :; }; check_os() { :; }
prepare_domains_tools() { DOMAINS_STAGE="$STAGE"; }
domains_tool() {
    if [[ "$1" == inspect ]]; then printf '%s\\n' '{"domains":{"panel":"deploy.example","reality":"cover.example"}}';
    else printf 'SWITCH|%s|%s|%s|%s\\n' "$2" "$3" "$4" "$5"; fi
}
entrypoint
'''
                script=root/'menu.sh';script.write_text(library)
                answers=('2' if language=='ru' else '1')+'\n2\n'+choice+'\n'+(panel+'\n' if choice in ('1','3') else '')+(reality+'\n' if choice in ('2','3') else '')+answer+'\n0\n'
                code,text=tty_run(script,answers.encode(),env={'STAGE':str(stage)})
                self.assertEqual(code,0,text)
                heading='CHANGE DOMAINS' if language=='en' else 'СМЕНА ДОМЕНОВ'
                self.assertIn(f'{PROJECT_FRAME_START}{FRAME}\n\n  {heading}\n',text.replace('\r\n','\n'))
                self.assertIn('Current Panel:   deploy.example' if language=='en' else 'Текущий домен панели:  deploy.example',text)
                self.assertIn('Current REALITY: cover.example' if language=='en' else 'Текущий домен REALITY: cover.example',text)
                self.assertIn('client configurations' if language=='en' else 'Клиентские конфигурации',text)
                self.assertIn('YES',text)
                if answer=='YES':
                    self.assertIn('SWITCH|'+panel+'|'+reality+'|deploy.example|cover.example',text)
                    self.assertEqual(text.count('1. Installation' if language=='en' else '1. Установка'),1,text)
                    result=text.split('DOMAINS CHANGED SUCCESSFULLY' if language=='en' else 'СМЕНА ДОМЕНОВ УСПЕШНО ЗАВЕРШЕНА')[1]
                    self.assertEqual('  REALITY:' in result,choice in ('2','3'))
                    self.assertEqual(('  Panel:' if language=='en' else '  Панель:') in result,choice in ('1','3'))
                else:self.assertNotIn('SWITCH|',text);self.assertIn('Cancelled.' if language=='en' else 'Отменено.',text)


    def test_telegram_companion_menu_return_failure_and_languages(self):
        with tempfile.TemporaryDirectory() as temporary:
            script=Path(temporary)/'entry.sh'
            script.write_text('source "'+str(ROOT/'x-ui-latest.sh')+'"\n'+'''
recover_domain_operation() { :; }
telegram_manager_action() { [[ -t 0 && -t 1 ]] || return 90; echo COMPANION; [[ ${COMPANION_EXIT:-0} == 0 ]] && ui_complete; return "${COMPANION_EXIT:-0}"; }
entrypoint
''')
            for language in ('1','2'):
                code,text=tty_run(script,(language+'\n4\n0\n').encode())
                self.assertEqual(code,0,text);self.assertIn('4. Telegram Web Proxy Manager',text)
                self.assertEqual(text.count('COMPANION'),1)
                self.assertEqual(text.count('1. Installation' if language=='1' else '1. Установка'),1)
            code,text=tty_run(script,b'1\n4\n',env={'COMPANION_EXIT':'42'})
            self.assertEqual(code,42,text)


class ManagerBackup(unittest.TestCase):
    def setUp(self):
        from test_personal_backup import PersonalBackup
        self.f=PersonalBackup('runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)

    def server_details_fixture(self):
        root = self.f.root/'details'
        db_path = root/'etc/x-ui/x-ui.db'
        db_path.parent.mkdir(parents=True)
        self.marker = db_path.parent/'auto-nginx-managed.json'
        self.marker.write_text(json.dumps(dict(format=1, layout='nginx-stream-v1', installed_by='source@'+'a'*40,
            domains=dict(panel='panel.example', reality='cover.example', vision='vision.example'),
            inbound_roles=dict(reality=1, vision=2), features=dict(adguard=False))))
        with sqlite3.connect(db_path) as db:
            db.executescript('''
                CREATE TABLE settings(key TEXT, value TEXT);
                CREATE TABLE users(id INTEGER, username TEXT, password TEXT);
                CREATE TABLE inbounds(id INTEGER, protocol TEXT, stream_settings TEXT, enable INTEGER);
                CREATE TABLE clients(id INTEGER, sub_id TEXT, enable INTEGER);
                CREATE TABLE client_inbounds(client_id INTEGER, inbound_id INTEGER);
                INSERT INTO users VALUES (1, 'panel-user', 'private-panel-sentinel');
                INSERT INTO inbounds VALUES
                    (1, 'vless', '{"realitySettings":{"serverNames":["cover.example"]}}', 1),
                    (2, 'vless', '{"tlsSettings":{"serverName":"vision.example"}}', 1),
                    (3, 'trojan', '{}', 0);
                INSERT INTO clients VALUES (1, 'private-sub-id', 1), (2, 'private-sub-id', 1),
                    (3, 'private-disabled-id', 0), (4, 'private-no-route-id', 1), (5, '', 1);
                INSERT INTO client_inbounds VALUES (1,1), (1,2), (2,1), (3,1), (4,3), (5,1);
            ''')
            db.executemany('INSERT INTO settings VALUES (?,?)', dict(
                webCertFile='/root/cert/panel.example/fullchain.pem', webBasePath='/panel/',
                subURI='https://panel.example:443/sub/?token=private-query-sentinel', subPath='/sub/', subEnable='true',
                subJsonURI='https://panel.example/json/', subJsonPath='/json/', subJsonEnable='false').items())
        nginx = root/'etc/nginx'
        for name in ('sites-enabled', 'sites-available', 'snippets/x-ui-auto-optional'):
            (nginx/name).mkdir(parents=True)
        (nginx/'sites-enabled/panel.example').symlink_to('../sites-available/panel.example')
        (nginx/'sites-available/panel.example').write_text('''
location /panel/ {}
location = /panel/diag {}
include /etc/nginx/snippets/includes.conf;
include /etc/nginx/snippets/x-ui-auto-optional/*.conf;
''')
        (nginx/'snippets/includes.conf').write_text('location /sub/ {}\nlocation /json/ {}\n')
        script = self.f.root/'details.sh'
        source = (ROOT/'x-ui-latest.sh').read_text().replace('XUIDB="/etc/x-ui/x-ui.db"', f'XUIDB="{db_path}"')
        source = source.replace('"${2:-/}" <<\'SERVER_DETAILS\'', f'"${{2:-{root}}}" <<\'SERVER_DETAILS\'')
        script.write_text(source)
        return root, db_path, script

    def test_server_details_active_wal_subscriptions_output_and_colors(self):
        import hashlib
        root, path, script = self.server_details_fixture()
        def files():
            return {p.relative_to(root):(hashlib.sha256(p.read_bytes()).digest(),p.stat().st_mtime_ns)
                    for p in root.rglob('*') if p.is_file() and p.name not in ('x-ui.db-wal','x-ui.db-shm')}

        with sqlite3.connect(path) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute("UPDATE clients SET enable=1 WHERE id=3")
            writer.commit()
            self.assertTrue(Path(str(path)+'-wal').is_file())
            before = files()
            for language, env, runs_color in (
                    ('1', {'TERM':'xterm','NO_COLOR':None}, True),
                    ('2', {'TERM':'xterm','NO_COLOR':''}, False),
                    ('1', {'TERM':'dumb','NO_COLOR':None}, False)):
                with self.subTest(language=language, env=env):
                    code, text = tty_run(script, (language+'\n6\n0\n').encode(), env=env)
                    self.assertEqual(code, 0)
                    self.assertEqual('\x1b' in text, runs_color)
                    if runs_color:
                        self.assertIn('Address:      \x1b[38;5;208mhttps://panel.example/panel/\x1b[0m', text)
                        self.assertIn('\x1b[1;36m  Subscriptions', text)
                        self.assertIn('\x1b[1;33m    not installed', text)
                        self.assertIn('\x1b[2m  Passwords are stored', text)
                    plain = re.sub(r'\x1b\[[0-9;]*m','',text)
                    for value in ('panel-user','https://panel.example/panel/diag','https://panel.example:443/sub/',
                                  'https://panel.example/json/','cover.example','vision.example'):
                        self.assertIn(value, plain)
                    self.assertRegex(plain, r'(?:Active|Активных):\s+2\r?\n')
                    self.assertIn('not enabled' if language == '1' else 'не включён', plain)
                    for secret in ('private-panel-sentinel','private-sub-id','private-disabled-id',
                                   'private-no-route-id','private-query-sentinel','sub_id'):
                        self.assertFalse(secret in text, 'Private field leaked from the details screen')
            env = {k:v for k,v in os.environ.items() if k != 'NO_COLOR'}
            redirected = subprocess.check_output(['bash','-c','source "$1"; server_details_action',
                                                   'fixture',str(script)],env={**env,'TERM':'xterm'},text=True)
            self.assertNotIn('\x1b', redirected)
            self.assertIn('-'*60, redirected)
            self.assertEqual(files(), before)

    def test_server_details_on_installer_layout_without_ws_grpc(self):
        from test_domains import DomainFixture

        fixture = DomainFixture(self.f.root/'details-core', ws_grpc='n')
        db = fixture.p(fixture.module.DB)
        marker = json.loads(fixture.p(fixture.module.MANIFEST).read_text())
        self.assertEqual(set(marker['inbound_roles']), {'reality', 'xhttp', 'hysteria2'})
        with sqlite3.connect(db) as connection:
            connection.execute("INSERT INTO settings(key,value) VALUES ('subEnable','true'),('subJsonEnable','true')")
        script = self.f.root/'details-core.sh'
        source = (ROOT/'x-ui-latest.sh').read_text().replace('XUIDB="/etc/x-ui/x-ui.db"', f'XUIDB="{db}"')
        source = source.replace('"${2:-/}" <<\'SERVER_DETAILS\'', f'"${{2:-{fixture.root}}}" <<\'SERVER_DETAILS\'')
        script.write_text(source)
        before = fixture.state()
        code, output = tty_run(script, b'1\n6\n0\n', env={'NO_COLOR':'1'})
        self.assertEqual(code, 0, output)
        for public in ('https://deploy.example/panel/', 'https://deploy.example/subscription/',
                       'https://deploy.example/jsonsub/'):
            self.assertIn(public, output)
        self.assertRegex(output, r'Active:\s+1\r?\n')
        self.assertFalse(any(secret in output for secret in ('fixture-sub', 'fixture-hash', 'fixture-uuid')))
        self.assertEqual(fixture.state(), before)

    def test_server_details_missing_foreign_and_busy_database(self):
        _, path, script = self.server_details_fixture()
        saved = self.marker.read_bytes()
        path.rename(path.with_suffix('.saved'))
        for language, expected in (('1','3X-UI AUTO NGINX server not found.'),
                                   ('2','Сервер 3X-UI AUTO NGINX не найден.')):
            code, text = tty_run(script, (language+'\n6\n0\n').encode())
            self.assertEqual(code, 0)
            self.assertIn(expected, text)
        path.with_suffix('.saved').rename(path)
        for marker in (None, b'invalid JSON', saved):
            with self.subTest(marker=marker):
                if marker is None:
                    self.marker.unlink()
                else:
                    self.marker.write_bytes(marker)
                if marker == saved:
                    with sqlite3.connect(path) as db:
                        db.execute('ALTER TABLE users RENAME TO foreign_users')
                code, text = tty_run(script, b'2\n6\n0\n')
                self.assertEqual(code, 0)
                plain = ' '.join(text.split())
                self.assertIn('Сервер не распознан как установленный этим проектом.', plain)
                self.assertIn('Установка его сотрёт.', plain)
                self.assertNotIn('https://', text)
        with sqlite3.connect(path) as writer:
            writer.execute('ALTER TABLE foreign_users RENAME TO users')
            writer.execute('BEGIN EXCLUSIVE')
            code, text = tty_run(script, b'1\n6\n0\n')
            self.assertEqual(code, 0)
            self.assertIn('Could not read a consistent view', text)
            self.assertEqual(text.count('6. My server details'), 2)
            self.assertNotIn('https://', text)

    def test_server_details_adguard_legacy_and_random_paths(self):
        root, path, script = self.server_details_fixture()
        with sqlite3.connect(path) as db:
            db.execute("DELETE FROM settings WHERE key='subJsonURI'")
        state = json.loads(self.marker.read_bytes())
        state['installed_by'] = 'legacy-v2.1.7-layout'
        state['features']['adguard'] = True
        state['domains']['vision'] = None
        state['inbound_roles'].pop('vision')
        self.marker.write_text(json.dumps(state))
        agh = root/'opt/AdGuardHome'
        agh.mkdir(parents=True)
        (agh/'AdGuardHome.yaml').write_text('users:\n  - name: "current-agh-user" # inline comment\n    password: private-agh-sentinel\n')
        helper = root/'usr/local/lib/3x-ui-pro/managed-adguard.sh'
        helper.parent.mkdir(parents=True)
        helper.write_bytes((ROOT/'assets/adguard/managed.sh').read_bytes())
        snippet = root/'etc/nginx/snippets/x-ui-auto-optional/adguard.conf'
        metadata = dict(domain='panel.example', path='adg-AbCdEf123456', web_port=18081)
        for doh, variant in (('dns-query','legacy'), ('dns-query','pre-ip-headers'),
                             ('dns-AbCdEf123456','pre-ip-headers'), ('dns-AbCdEf123456','')):
            with self.subTest(doh=doh, variant=variant):
                (agh/'managed.json').write_text(json.dumps(metadata if doh == 'dns-query' else dict(metadata,doh_path=doh)))
                snippet.write_bytes(subprocess.check_output(['bash','-c',
                    'source "$1"; AGH_PATH=$2 AGH_WEB_PORT=18081 AGH_DOH_PATH=$3 agh_snippet "$4"',
                    'fixture',str(helper),metadata['path'],doh,variant]))
                code, text = tty_run(script, b'2\n6\n0\n')
                self.assertEqual(code, 0)
                self.assertIn('https://panel.example/'+doh, text)
                self.assertIn('current-agh-user', text)
                self.assertNotIn('inline comment', text)
                self.assertFalse('private-agh-sentinel' in text, 'AGH password leaked')
                self.assertRegex(text, r'Адрес JSON:\s+не найдено')
                self.assertRegex(text, r'Vision:\s+не настроен')
        snippet.write_text(snippet.read_text().replace('proxy_buffering off;', 'proxy_buffering on;'))
        code, text = tty_run(script, b'1\n6\n0\n')
        self.assertEqual(code, 0)
        self.assertRegex(text, r'DoH:\s+not found')
        self.assertNotIn('https://panel.example/dns-AbCdEf123456', text)

    def test_server_details_dot_uses_file_and_stays_read_only(self):
        root, db, script = self.server_details_fixture()
        fragment = root/'etc/nginx/stream-dot.d/adguard-dot.conf'
        fragment.parent.mkdir()
        for installed in (False, True):
            if installed:
                fragment.touch()
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in (db, self.marker, *([fragment] if installed else []))}
            for language, enabled, disabled in (
                (b'1', 'panel.example, port 853', 'not enabled'),
                (b'2', 'panel.example, порт 853', 'не включён'),
            ):
                with self.subTest(installed=installed, language=language):
                    code, text = tty_run(script, language+b'\n6\n0\n')
                    self.assertEqual(code, 0, text)
                    self.assertRegex(text, r'DoT:\s+'+re.escape(enabled if installed else disabled))
                    self.assertNotIn('private-panel-sentinel', text)
            self.assertEqual(fragment.exists(), installed)
            self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before})

    def test_telegram_installed_always_refreshes_bootstrap(self):
        root=self.f.root;launcher=root/'launcher';marker=root/'handoff';network=root/'downloads'
        launcher.write_text('#!/bin/bash\nprintf stale > "$MARKER"\n');launcher.chmod(0o755)
        original=launcher.read_bytes()
        library=root/'library'
        library.write_text((ROOT/'x-ui-latest.sh').read_text().replace('/usr/local/bin/telegram-web-proxy-manager',str(launcher)))
        script='source "'+str(library)+'"\n'+'''
acquire_stack_lock() { return 99; }
curl() {
    printf '%s\n' "$*" >> "$NETWORK"
    printf '%s' "${BODY-fixture}" > "${@: -1}"
    return "${DOWNLOAD_EXIT:-0}"
}
bash() { [[ $# == 1 ]] || return 91; cat "$1" > "$MARKER"; return "${BOOTSTRAP_EXIT:-0}"; }
telegram_manager_action
'''
        for body in ('current-main-1','current-main-2'):
            result=subprocess.run(['bash','-c',script],input='',text=True,capture_output=True,
                env={**os.environ,'MARKER':str(marker),'NETWORK':str(network),'BODY':body})
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(marker.read_text(),body)
            self.assertEqual(launcher.read_bytes(),original)
        self.assertEqual(len(network.read_text().splitlines()),2)
        self.assertIn('/telegram-web-proxy-manager/main/install.sh',network.read_text())
        for env,code in (({'DOWNLOAD_EXIT':'23'},23),({'BODY':''},1),({'BOOTSTRAP_EXIT':'42'},42)):
            marker.unlink(missing_ok=True)
            result=subprocess.run(['bash','-c',script],text=True,capture_output=True,
                env={**os.environ,'MARKER':str(marker),'NETWORK':str(network),**env})
            self.assertEqual(result.returncode,code)
            self.assertTrue(result.stderr.strip())
            if 'BOOTSTRAP_EXIT' not in env:self.assertFalse(marker.exists())
            self.assertEqual(launcher.read_bytes(),original)

    def test_telegram_companion_safe_handoff_and_bootstrap(self):
        root=self.f.root
        launcher=root/'launcher'
        osfile=root/'os-release';osfile.write_text('ID=ubuntu\nVERSION_ID=24.04\n')
        db=root/'db';db.touch();nginx=root/'nginx.conf';nginx.touch();stream=root/'stream.conf';stream.touch()
        marker=root/'external';network=root/'network'
        source=(ROOT/'x-ui-latest.sh').read_text()
        for old,new in (('/usr/local/bin/telegram-web-proxy-manager',str(launcher)),('/etc/os-release',str(osfile)),
                        ('/etc/x-ui/x-ui.db',str(db)),('/etc/nginx/nginx.conf',str(nginx)),
                        ('/etc/nginx/stream-enabled/stream.conf',str(stream))):
            source=source.replace(old,new)
        library=root/'library';library.write_text(source)
        # Download only fixture bytes; bash handoff is intercepted, never installs.
        setup='source "'+str(library)+'"\n'+'''
acquire_stack_lock() { return 99; }
systemctl() { return "${ACTIVE_EXIT:-0}"; }
nginx() {
    [[ $* == '-t -q' ]] || { echo nginx-success-noise; return 92; }
    [[ ${NGINX_EXIT:-0} == 0 ]] || { echo nginx-real-error >&2; return "$NGINX_EXIT"; }
}
curl() { printf '%s\n' "$*" > "$NETWORK"; [[ ${DOWNLOAD_EXIT:-0} == 0 ]] || return "$DOWNLOAD_EXIT"; printf fixture > "${@: -1}"; }
bash() { [[ $# == 1 && -f $1 ]] || return 91; printf bootstrap > "$MARKER"; return "${EXTERNAL_EXIT:-0}"; }
telegram_manager_action
'''
        self.assertIn('/telegram-web-proxy-manager/main/install.sh',source)
        def run(answer='y\n',**env):
            marker.unlink(missing_ok=True);network.unlink(missing_ok=True)
            return subprocess.run(['bash','-c',setup],input=answer,text=True,capture_output=True,
                                  env={**os.environ,'MARKER':str(marker),'NETWORK':str(network),**env})
        for answer in ('','\n','n\n'):
            self.assertEqual(run(answer).returncode,0);self.assertFalse(network.exists());self.assertFalse(marker.exists())
        self.assertEqual(run().returncode,0);self.assertEqual(marker.read_text(),'bootstrap')
        self.assertNotIn('--version',network.read_text())
        self.assertNotIn('nginx-success-noise',run().stdout)
        failure=run(NGINX_EXIT='1')
        self.assertNotEqual(failure.returncode,0);self.assertIn('nginx-real-error',failure.stderr)
        entry=root/'tty-entry'
        entry.write_text(setup.removesuffix('telegram_manager_action\n')+"recover_domain_operation() { :; }\nentrypoint\n")
        def menu(answers,code=0):
            env={'MARKER':str(marker),'NETWORK':str(network)}
            result,text=tty_run(entry,answers,env=env)
            self.assertEqual(result,code,text)
            return text
        for language in ('1','2'):
            text=menu((language+'\n4\ny\n').encode())
            self.assertEqual(text.count('1. Installation' if language=='1' else '1. Установка'),1)
            self.assertIn('Would you like to proceed with installing' if language=='1' else 'Хотите перейти к установке',text)
            for answer in ('n\n0\n','\n0\n','\x040\n'):
                text=menu((language+'\n4\n'+answer).encode())
                self.assertEqual(text.count('1. Installation' if language=='1' else '1. Установка'),2)

        for env,code in (({'DOWNLOAD_EXIT':'23'},23),({'EXTERNAL_EXIT':'42'},42),({'ACTIVE_EXIT':'1'},1),({'NGINX_EXIT':'1'},1)):
            self.assertEqual(run(**env).returncode,code)
        for osdata in ('ID=debian\nVERSION_ID=13\n','ID=ubuntu\nVERSION_ID=22.04\n'):
            osfile.write_text(osdata);self.assertNotEqual(run().returncode,0);self.assertFalse(network.exists())
        osfile.write_text('ID=ubuntu\nVERSION_ID=26.04\n')
        db.unlink();self.assertNotEqual(run().returncode,0);self.assertFalse(network.exists())
        launcher.write_text('#!/bin/bash\nprintf launcher > "$MARKER"\nexit "${EXTERNAL_EXIT:-0}"\n');launcher.chmod(0o755)
        self.assertEqual(run(ACTIVE_EXIT='1').returncode,0);self.assertEqual(marker.read_text(),'bootstrap');self.assertTrue(network.exists())
        self.assertEqual(run(EXTERNAL_EXIT='43').returncode,43)
        for language in ('1','2'):
            text=menu((language+'\n4\n').encode())
            self.assertEqual(text.count('1. Installation' if language=='1' else '1. Установка'),1)
        for mode in (0o777,0o775,0o644):
            launcher.chmod(mode);self.assertNotEqual(run().returncode,0);self.assertFalse(marker.exists())
        launcher.chmod(0o755);os.chown(launcher,1000,1000)
        self.assertNotEqual(run().returncode,0);self.assertFalse(marker.exists())
        launcher.unlink();launcher.symlink_to('/bin/true')
        self.assertNotEqual(run().returncode,0);self.assertFalse(network.exists())

    def test_russian_backup_restore_confirmation_status_and_partial_messages(self):
        from test_personal_backup import relocated, TWPM_RESTORE_EN, TWPM_RESTORE_RU
        root=self.f.root;helper=self.f.path('/usr/local/bin/x-ui-backup')
        helper.parent.mkdir(parents=True,exist_ok=True)
        helper.write_text('''#!/bin/bash
case "$1" in
    inspect) printf '{"format_version":3}\\n' ;;
    backup) printf '{"status":"success","archive":"%s/var/backups/x-ui/fixture.tar.gz"}\\n' "$FIXTURE_ROOT" ;;
    restore) printf restored > "$FIXTURE_ROOT/restored"; exit "${RESTORE_EXIT:-0}" ;;
    telemt-check) exit "${TELEMT_CHECK:-0}" ;;
esac
''');helper.chmod(0o755)
        self.f.path('/var/backups/x-ui').mkdir(parents=True,exist_ok=True)
        self.f.path('/var/backups/x-ui/fixture.tar.gz').write_bytes(b'fixture')
        library=relocated((ROOT/'x-ui-latest.sh').read_text(),root)
        library=library.replace(str(root)+'/proc/','/proc/').replace('/run/3x-ui-auto-nginx',str(root)+'/run/3x-ui-auto-nginx')
        script=root/'ru-menu.sh'
        script.write_text(library[:library.rindex('if [[ ${BASH_SOURCE[0]}')]+'''
prepare_backup_helper() { :; }
prepare_restore_security() { :; }
if [[ ${PARTIAL_SECURITY:-0} == 1 ]]; then
    post_restore_security() { printf 'Security: PARTIAL\\nOverall: PARTIAL\\n'; return 1; }
fi
entrypoint
''')
        code,text=tty_run(script,b'2\n3\n1\n0\n0\n',env=self.f.env)
        self.assertEqual(code,0,text);self.assertIn('РЕЗЕРВНАЯ КОПИЯ СОЗДАНА',text);self.assertIn('Архив создан и проверен',text);self.assertEqual(text.count('1. Установка'),2)
        original=self.f.path('/etc/x-ui/x-ui.db').read_bytes()
        for answers,flags,expected,restored in (
                ('y\ny\nyes\n',{},0,False),('n\nn\nДА\n',{},0,False),
                ('n\nn\n\x04',{},0,False),('n\nn\nYES\n',{},0,True),
                ('n\nn\nYES\n',{'RESTORE_EXIT':'42'},42,True),
                ('y\ny\nYES\n',{'PARTIAL_SECURITY':'1'},1,True)):
            with self.subTest(answers=answers,flags=flags):
                (root/'restored').unlink(missing_ok=True)
                code,text=tty_run(script,('2\n3\n3\n/archive.tar.gz\n'+answers+'0\n0\n').encode(),env={**self.f.env,**flags})
                self.assertEqual(code,expected,text);self.assertEqual((root/'restored').exists(),restored)
                for prompt in ('Номер архива или абсолютный путь','Автоматическая перезагрузка разрешена в 04:38',
                               'Fail2ban для SSH? [y/N]','Включить UFW с защитой доступа по SSH','введите YES'):
                    self.assertIn(prompt,text)
                self.assertNotIn('{"format_version":3}',text);self.assertIn('Формат: Backup v3',text)
                self.assertIn(f'{YES_RU} {FRAME} {YES_RU_PROMPT}',' '.join(text.replace(str(root),'').split()))  # the fixture relocates paths into its root
                self.assertEqual(self.f.path('/etc/x-ui/x-ui.db').read_bytes(),original)
                if not restored and '\x04' not in answers:self.assertIn('Отменено.',text)
                if flags.get('RESTORE_EXIT'):
                    self.assertIn('Restore: FAILED (exit 42)',text);self.assertNotIn('Restore: SUCCESS',text)
                elif restored:
                    self.assertIn('Restore: SUCCESS',text)
                    self.assertIn('Overall: PARTIAL' if expected else 'Overall: SUCCESS',text)
                    self.assertEqual(text.count('1. Установка'),1,text)
                    if expected:self.assertIn('данные сохранены, но настройка Security не завершена',text)

        # TWPM found (helper exit 10): translated refusal before any question; nothing is restored.
        for choice,expected,absent in (('2',TWPM_RESTORE_RU,'Номер архива'),('1',TWPM_RESTORE_EN,'Archive number')):
            with self.subTest(twpm_language=choice):
                (root/'restored').unlink(missing_ok=True)
                code,text=tty_run(script,(choice+'\n3\n3\n0\n0\n').encode(),env={**self.f.env,'TELEMT_CHECK':'10'})
                flat=' '.join(text.split())
                self.assertIn(f'{FRAME} [FAIL] {FRAME} {expected} {FRAME}',flat)
                # One language per choice: the other language's text is absent.
                self.assertNotIn(TWPM_RESTORE_EN if choice=='2' else TWPM_RESTORE_RU,flat)
                self.assertNotIn(absent,text);self.assertFalse((root/'restored').exists())
                self.assertEqual(self.f.path('/etc/x-ui/x-ui.db').read_bytes(),original)
        # Any other helper status (for example an old helper without the command) continues to the archive question.
        code,text=tty_run(script,b'1\n3\n3\n0\n0\n',env={**self.f.env,'TELEMT_CHECK':'1'})
        self.assertIn('Archive number',text);self.assertNotIn('Telegram Web Proxy Manager (TWPM) was found',text)
        code,text=tty_run(script,b'1\n3\n3\n/archive.tar.gz\nn\nn\nyes\n0\n0\n',env=self.f.env)
        self.assertIn(f'{YES_EN} {FRAME} {YES_EN_PROMPT}',' '.join(text.replace(str(root),'').split()));self.assertFalse((root/'restored').exists())

    def test_dot_restore_menu_warns_once_in_selected_language_after_result(self):
        from test_adguard_backup import AdGuardBackup
        from test_personal_backup import relocated

        # This class runs after the parallel root shards because Restore scans
        # process arguments for other Backup utilities.
        adguard = AdGuardBackup('runTest')
        adguard.setUp()
        self.addCleanup(adguard.doCleanups)
        f = adguard.fixture
        archive, _, _ = adguard.dot_archive()
        manager = f.root/'manager.sh'
        manager.write_text(relocated((ROOT/'x-ui-latest.sh').read_text(), f.root))
        f.write('/usr/local/bin/x-ui-backup', f.script.read_text(), 0o755)
        completion = f.root/'restore-completion'
        code = '''
source "$1"
prepare_backup_helper() { :; }
acquire_stack_lock() { :; }
recover_domain_operation() { :; }
UI_LANG=$2 UI_INTERACTIVE=1 UI_COMPLETION_FD=3 backup_action restore 3>"$3"
'''
        messages = {
            'en': ('RESTORE RESULT', 'DoT was restored.', 'firewall rule blocks 853/tcp', 'Phones using Private DNS'),
            'ru': ('РЕЗУЛЬТАТ ВОССТАНОВЛЕНИЯ', 'DoT восстановлен.', 'Порт 853/tcp закрыт', 'Телефоны с частным DNS'),
        }
        for language, (title, start, blocked, limited) in messages.items():
            for action in ('deny', 'reject', 'limit', None):
                with self.subTest(language=language, action=action):
                    result = subprocess.run(
                        ['bash', '-c', code, 'fixture', str(manager), language, str(completion)],
                        input=f'{archive}\nn\nn\nYES\n', text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        env={**f.env, 'NO_COLOR': '1', 'UFW_STATE': 'active',
                             'UFW_ADDED': f'ufw {action} 853/tcp' if action else ''}, timeout=60)
                    output = result.stdout
                    self.assertEqual(result.returncode, 0, output)
                    self.assertEqual(completion.read_text(), 'completed\n')
                    self.assertLess(output.index(title), output.index('Restore: SUCCESS'))
                    self.assertLess(output.index('Restore: SUCCESS'), output.index('Overall: SUCCESS'))
                    other = messages['ru' if language == 'en' else 'en'][1]
                    self.assertNotIn(other, output)
                    self.assertEqual(output.count(start), int(action is not None), output)
                    last = output.strip().splitlines()[-1]
                    if action:
                        self.assertTrue(last.startswith(start), output)
                        self.assertIn(limited if action == 'limit' else blocked, last)
                        self.assertNotIn(blocked if action == 'limit' else limited, last)
                        self.assertIn(f'ufw delete {action} 853/tcp', last)
                        self.assertIn('ufw allow 853/tcp', last)
                    else:
                        self.assertEqual(last, 'Overall: SUCCESS', output)

    def test_post_restore_security_trust_cleanup_status_lock_and_partial_result(self):
        from test_personal_backup import relocated
        root = self.f.root
        library = relocated((ROOT/'x-ui-latest.sh').read_text(), root)
        library = library.replace(str(root)+'/proc/', '/proc/').replace('/run/xui-restore-security', str(root)+'/run/xui-restore-security')
        library = library.replace('/run/3x-ui-auto-nginx', str(root)+'/run/3x-ui-auto-nginx')
        script = root/'manager.sh'; script.write_text(library)
        helper = self.f.path('/usr/local/bin/x-ui-backup'); helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text('''#!/bin/bash
case $1 in
 inspect) printf '{"format_version":3}\\n' ;;
 restore)
   printf restored > "$FIXTURE_ROOT/restored"
   mkdir -p "$FIXTURE_ROOT/usr/local/lib/3x-ui-pro"
   printf 'raise RuntimeError("ARCHIVE HELPER EXECUTED")' > "$FIXTURE_ROOT/usr/local/lib/3x-ui-pro/managed-security.py"
   echo 'Restore completed successfully.'
   trap 'exit "${RESTORE_EXIT:-0}"' EXIT ;;
esac
'''); helper.chmod(0o755)
        trusted = root/'trusted.py'
        trusted.write_text('''import json, os, pathlib, subprocess, sys
root = pathlib.Path(os.environ['FIXTURE_ROOT'])
assert sys.flags.isolated and pathlib.Path(__file__).parent.stat().st_mode & 0o777 == 0o700
assert (root/'restored').read_text() == 'restored'
assert subprocess.run(['flock','-n',str(root/'run/3x-ui-auto-nginx/operation.lock'),'true']).returncode != 0
with (root/'security-ran').open('a') as out: out.write('ufw' if sys.argv[1:] else 'apt')
if sys.argv[1:]: result = dict(status='preserved')
else: result = dict(status='partial' if os.environ.get('SECURITY_FAIL') else 'configured',
                   apt='failed_rolled_back' if os.environ.get('SECURITY_FAIL') else 'configured', fail2ban='configured')
print(json.dumps(result))
sys.exit(1 if result['status']=='partial' else 0)
''')
        code = '''source "$1"
prepare_backup_helper() { :; }
pin_project_source() { PROJECT_SOURCE_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; PROJECT_REF=$PROJECT_SOURCE_SHA; GITHUB_RAW=https://source.invalid/$PROJECT_SOURCE_SHA; }
curl() { [[ ${PREP_FAIL:-0} != 1 && "$*" == *aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/assets/security/managed.py* ]] || return 1; cp "$TRUSTED_HELPER" "${@: -1}"; touch "$FIXTURE_ROOT/prepared"; }
manager_menu
'''
        for scenario, answers, flags, expected, ran in (
            ('none', 'n\nn\nYES\n', {}, 0, ''),
            ('success', 'y\ny\nYES\n', {}, 0, 'aptufw'),
            ('partial', 'y\ny\nYES\n', {'SECURITY_FAIL':'1'}, 1, 'aptufw'),
            ('cleanup', 'y\ny\nYES\n', {'RESTORE_EXIT':'42'}, 42, ''),
            ('prep-continue', 'y\ny\nYES\ny\n', {'PREP_FAIL':'1'}, 0, ''),
            ('prep-cancel', 'y\ny\nYES\nn\n', {'PREP_FAIL':'1'}, 0, ''),
        ):
            with self.subTest(scenario=scenario):
                for name in ('security-ran', 'prepared', 'restored'): (root/name).unlink(missing_ok=True)
                result = subprocess.run(['bash','-c',code,'fixture',str(script)],
                    input='3\n3\n/archive.tar.gz\n'+answers+'0\n', text=True, capture_output=True,
                    env={**self.f.env, 'TRUSTED_HELPER':str(trusted), 'PYTHONPATH':str(root), **flags})
                self.assertEqual(result.returncode, expected, result.stdout+result.stderr)
                self.assertEqual((root/'security-ran').read_text() if (root/'security-ran').exists() else '', ran)
                self.assertFalse(list((root/'run').glob('xui-restore-security.*')))
                if scenario == 'partial':
                    self.assertIn('Restore: SUCCESS', result.stdout)
                    self.assertIn('Overall: PARTIAL', result.stdout)
                    self.assertNotIn('Overall: SUCCESS', result.stdout)
                    self.assertNotIn('Restore: FAILED', result.stdout)
                    self.assertEqual((root/'restored').read_text(), 'restored')
                elif scenario == 'cleanup':
                    self.assertNotIn('Restore: SUCCESS', result.stdout)
                elif scenario == 'none':
                    self.assertFalse((root/'prepared').exists())
                    self.assertNotIn('UFW:', result.stdout)
                elif scenario == 'prep-cancel': self.assertFalse((root/'restored').exists())

    def test_inherited_backup_json_keeps_default_cli(self):
        result=self.f.run_tool('backup',BACKUP_JSON='1')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Backup completed successfully.',result.stdout)
        self.assertNotIn('"status": "success"',result.stdout)
        archive=next(self.f.path('/var/backups/x-ui').glob('*.tar.gz'))
        self.assertEqual(self.f.run_tool('inspect',archive).returncode,0)

    def test_helper_refuses_writable_target_ancestry_before_execution_or_replacement(self):
        from test_personal_backup import function, relocated
        names=('backup_helper_path_safe','backup_helper_compatible','install_backup_tool','prepare_backup_helper')
        helpers='\n'.join(relocated(function(n),self.f.root).replace(' /usr ', ' '+str(self.f.root/'usr')+' ')
                          for n in names if n+'() {' in (ROOT/'x-ui-latest.sh').read_text())
        target=self.f.path('/usr/local/bin/x-ui-backup');target.parent.mkdir(parents=True,exist_ok=True)
        executed=self.f.root/'helper-executed'
        source='#!/bin/bash\ntouch "'+str(executed)+'"\ncase $1 in capabilities) echo "xui-backup:1 inspect backup-json lock-fd9";; lock-check) [[ -e /proc/$$/fd/9 ]] || exit 75;; esac\n'
        setup='msg_err() { echo "$*" >&2; }; pin_project_source() { GITHUB_RAW=https://source.invalid/exact; }; curl() { command cp "'+str(self.f.script)+'" "${@: -1}"; };\n'
        for directory in (target.parent,target.parent.parent,self.f.root/'usr'):
            for action in ('backup_helper_compatible','install_backup_tool','prepare_backup_helper'):
                with self.subTest(directory=directory.relative_to(self.f.root),action=action):
                    target.write_text(source);target.chmod(0o755);executed.unlink(missing_ok=True)
                    directory.chmod(0o775)
                    try:
                        result=subprocess.run(['bash','-c',self.lock_script('acquire_stack_lock || exit $?')+'\n'+helpers+'\n'+setup+action],capture_output=True,text=True)
                        self.assertNotEqual(result.returncode,0,result.stderr)
                        self.assertFalse(executed.exists(),'Helper in writable ancestry was executed')
                        self.assertEqual(target.read_text(),source)
                        self.assertEqual(directory.stat().st_mode&0o777,0o775)
                    finally:directory.chmod(0o755)

    def test_restore_menu_failure_stops_session_and_preserves_recovery_contract(self):
        import json
        from test_personal_backup import relocated
        archive=self.f.backup()
        self.f.write('/etc/x-ui/target-marker','previous target')
        before=json.loads((self.f.root/'services.json').read_text())
        helper=self.f.path('/usr/local/bin/x-ui-backup');helper.parent.mkdir(parents=True,exist_ok=True)
        helper.write_bytes(self.f.script.read_bytes());helper.chmod(0o755)
        library=relocated((ROOT/'x-ui-latest.sh').read_text(),self.f.root)
        library=library.replace(str(self.f.root)+'/proc/','/proc/').replace('/run/3x-ui-auto-nginx',str(self.f.root)+'/run/3x-ui-auto-nginx')
        library=library.replace(' /usr ', ' '+str(self.f.root/'usr')+' ')
        script=self.f.root/'menu.sh';script.write_text(library)
        for scenario,flags in (('pre-mutation',{'FAIL_NGINX':'1'}),
                               ('verified',{'FAIL_HEALTH_SERVICE':'mtr-backend','FAIL_ONCE':'1'}),
                               ('unverified',{'FAIL_HEALTH_SERVICE':'mtr-backend'})):
            with self.subTest(scenario=scenario):
                (self.f.root/'commands').write_text('');(self.f.root/'fault-used').unlink(missing_ok=True)
                code,text=tty_run(script,b'1\n3\n3\n'+str(archive).encode()+b'\nn\nn\nYES\n1\n',timeout=90,env={**self.f.env,**flags})
                self.assertNotEqual(code,0,text)
                self.assertIn('Restore: FAILED (exit ',text);self.assertNotIn('SUCCESS',text)
                self.assertEqual(text.count('1. Installation'),1)
                self.assertEqual(text.count('BACKUPS'),1)
                self.assertEqual(self.f.path('/etc/x-ui/target-marker').read_text(),'previous target')
                self.assertEqual(json.loads((self.f.root/'services.json').read_text()),before)
                retained=list(self.f.path('/var/backups/x-ui').glob('.rollback-*'))
                self.assertEqual(bool(retained),scenario=='unverified')
                if scenario=='pre-mutation':
                    self.assertFalse(any(c[:2]==['systemctl','stop'] for c in self.f.commands()))
                elif scenario=='verified':self.assertIn('Previous managed state/service states restored and checked',text)
                else:self.assertIn('Automatic rollback could not be verified',text)

    def test_inspect_machine_result_marker_and_historical_roundtrip(self):
        import hashlib,json
        marker=self.f.path('/etc/x-ui/auto-nginx-managed.json')
        marker.write_text('{"format":1,"installed_by":"source@fixture"}\n');marker.chmod(0o600)
        result=self.f.run_tool('backup','--json')
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout);self.assertEqual(value['status'],'success')
        archive=Path(value['archive']);self.assertTrue(archive.is_file())
        digest=hashlib.sha256(archive.read_bytes()).hexdigest()
        inspect=self.f.run_tool('inspect',archive)
        self.assertEqual(inspect.returncode,0,inspect.stderr)
        self.assertEqual(json.loads(inspect.stdout)['format_version'],3)
        self.assertNotIn('hostname',json.loads(inspect.stdout))
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),digest)
        marker.unlink()
        restore=self.f.run_tool('restore',archive)
        self.assertEqual(restore.returncode,0,restore.stderr)
        self.assertEqual(marker.read_text(),'{"format":1,"installed_by":"source@fixture"}\n')
        self.assertEqual(marker.stat().st_mode&0o777,0o600)

    def test_inspect_untrusted_metadata_and_failure_result_preserves_archive(self):
        import gzip,io,json,tarfile
        archive=self.f.backup();rewritten=archive.with_name('unsafe-display.tar.gz')
        with tarfile.open(archive) as src,tarfile.open(rewritten,'w:gz') as dst:
            for member in src:
                data=src.extractfile(member).read() if member.isfile() else None
                if member.name=='meta.json':
                    meta=json.loads(data);meta['created']='\x1b[31m\nsecret';meta.pop('service_states',None)
                    data=json.dumps(meta).encode();member.size=len(data)
                dst.addfile(member,io.BytesIO(data) if data is not None else None)
        result=self.f.run_tool('inspect',rewritten)
        self.assertEqual(result.returncode,0,result.stderr);self.assertNotIn('\x1b',result.stdout)
        self.assertEqual(json.loads(result.stdout)['created'],'\x1b[31m\nsecret')
        # Close the result writer's descriptor only after archive publication.
        before=set(self.f.path('/var/backups/x-ui').glob('*.tar.gz'))
        script="source \"$1\"; python3() { if [[ $# == 2 && $2 == *.tar.gz ]]; then command python3 -c 'import os,sys; os.close(1); exec(sys.stdin.read())' \"${@:2}\"; else command python3 \"$@\"; fi; }; main backup --json"
        result=subprocess.run(['bash','-c',script,'fixture',str(self.f.script)],env=self.f.env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        published=set(self.f.path('/var/backups/x-ui').glob('*.tar.gz'))-before
        self.assertEqual(len(published),1)
        self.assertEqual(self.f.run_tool('inspect',published.pop()).returncode,0)

    def lock_script(self,tail):
        from test_personal_backup import function
        lock=function('acquire_stack_lock').replace('/run/3x-ui-auto-nginx',str(self.f.root)+'/run/3x-ui-auto-nginx')
        return lock+'\n'+tail

    def test_real_concurrent_operation_pairs_and_nested_ownership(self):
        import itertools,signal
        # Every production mutating dispatcher calls the same boundary.
        from test_personal_backup import function
        self.assertIn('acquire_stack_lock',(ROOT/'x-ui-latest.sh').read_text().split('run_installation() (')[1].split('manager_menu()')[0])
        self.assertIn('acquire_stack_lock',(ROOT/'assets/backup/x-ui-backup.sh').read_text().split('main() {')[1])
        def dispatch(operation, hold):
            action=': > "$READYFILE"; read -r done' if hold else 'echo MUTATED'
            if operation in ('backup','restore'):
                return 'source "'+str(self.f.script)+'"; cmd_backup() { '+action+'; }; cmd_restore() { '+action+'; }; main '+operation
            library=(ROOT/'x-ui-latest.sh').read_text()
            library=library[:library.rindex('if [[ ${BASH_SOURCE[0]}')]
            library=library.replace('/run/3x-ui-auto-nginx',str(self.f.root)+'/run/3x-ui-auto-nginx')
            if operation=='domains':library=library.replace('/etc/x-ui/x-ui.db',str(self.f.path('/etc/x-ui/x-ui.db')))
            copy=self.f.root/'installer.sh';copy.write_text(library)
            if operation=='domains':
                return 'source "'+str(copy)+'"; check_os() { :; }; prepare_domains_tools() { '+action+'; return 1; }; change_domains_action'
            return 'source \"'+str(copy)+'\"; check_os() { :; }; check_cpu() { :; }; initialize_installation() { :; }; ip() { echo \"src 127.0.0.1\"; }; confirm_destructive_reinstall() { :; }; main() { '+action+'; }; run_installation -install y'
        for first,second in itertools.product(('backup','restore','install','domains'),repeat=2):
            with self.subTest(first=first,second=second):
                ready=self.f.root/'ready';ready.unlink(missing_ok=True)
                holder=subprocess.Popen(['bash','-c',dispatch(first,True),'fixture',str(ready)],
                                         stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={**os.environ,'READYFILE':str(ready)})
                try:
                    deadline=time.monotonic()+3
                    while not ready.exists() and holder.poll() is None and time.monotonic()<deadline:time.sleep(.01)
                    self.assertTrue(ready.exists())
                    other=subprocess.run(['bash','-c',dispatch(second,False)],capture_output=True,text=True)
                    self.assertEqual(other.returncode,75,other.stderr);self.assertNotIn('MUTATED',other.stdout)
                finally:holder.communicate('\n',timeout=5)
        # Real nested helper inherits fd 9; an independent open description cannot fake it.
        result=subprocess.run(['bash','-c',self.lock_script('acquire_stack_lock || exit $?; bash "$1" lock-check; exit $?'),
                               'fixture',str(self.f.script)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        # An environment flag never bypasses contention; no such input exists.
        result=subprocess.run(['bash','-c',self.lock_script('acquire_stack_lock || exit $?; bash "$1" lock-check 9>&-; exit $?'),
                               'fixture',str(self.f.script)],capture_output=True,text=True,env={**os.environ,'XUI_SKIP_LOCK':'1'})
        self.assertEqual(result.returncode,75,result.stderr)

    def test_lock_lasts_through_child_failure_and_is_released_by_kernel(self):
        ready=self.f.root/'ready'
        child=self.f.root/'child'
        child.write_text(self.lock_script('acquire_stack_lock || exit $?; : > "$1"; read -r done; exit 42'))
        proc=subprocess.Popen(['bash','-c',self.lock_script('acquire_stack_lock || exit $?; bash "$1" "$2"; exit $?'),
                               'fixture',str(child),str(ready)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        deadline=time.monotonic()+3
        while not ready.exists() and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue(ready.exists());proc.terminate();proc.wait(timeout=3)
        blocked=self.f.run_tool('lock-check');self.assertEqual(blocked.returncode,75,blocked.stderr)
        proc.stdin.write('\n');proc.stdin.flush();proc.stdin.close()
        # Wait for the inherited writer to finish without arbitrary readiness sleep.
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            result=self.f.run_tool('lock-check')
            if result.returncode==0:break
        self.assertEqual(result.returncode,0,result.stderr)
        proc.stdout.close();proc.stderr.close()

    def test_managed_state_actual_roles_partial_features_and_atomic_failure(self):
        import json,sqlite3
        from test_personal_backup import function
        from test_personal_xhttp import inbounds
        dbpath=self.f.path('/etc/x-ui/x-ui.db')
        with sqlite3.connect(dbpath) as db:
            db.execute('DROP TABLE inbounds');db.execute('DROP TABLE hosts')
            db.execute('CREATE TABLE inbounds(id INTEGER PRIMARY KEY,protocol,listen,port,stream_settings,share_addr_strategy,share_addr)')
            db.execute('CREATE TABLE hosts(inbound_id,address,port)')
            for key,name in (('webCertFile','fullchain.pem'),('webKeyFile','privkey.pem'),('subCertFile','fullchain.pem'),('subKeyFile','privkey.pem')):
                db.execute('UPDATE settings SET value=? WHERE key=?',('/root/cert/example.com/'+name,key))
            for iid,(role,row) in enumerate(inbounds(domain='example.com',reality_domain='reality.example.com').items(),20):
                db.execute('INSERT INTO inbounds VALUES(?,?,?,?,?,?,?)',(iid,row['protocol'],row['listen'],int(row['port']),row['stream_settings'],'',''))
                db.execute('INSERT INTO hosts VALUES(?,?,443)',(iid,'reality.example.com' if role=='hysteria2' else 'example.com'))
        code='CORE_RESULT=configured; PROJECT_SOURCE_SHA='+('a'*40)+'; domain=example.com; reality_domain=reality.example.com; XUIDB="$1"; VISION_RESULT=failed_rolled_back; AWG_RESULT=not_requested; AGH_RESULT=failed_unverified;\n'+function('write_managed_state')+'\nwrite_managed_state'
        result=subprocess.run(['bash','-c',code,'fixture',str(dbpath)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        marker=dbpath.parent/'auto-nginx-managed.json';old=marker.read_bytes();state=json.loads(old)
        self.assertEqual(set(state['inbound_roles']),{'reality','ws','grpc','xhttp','hysteria2'})
        self.assertTrue(all(i>=20 for i in state['inbound_roles'].values()))
        self.assertFalse(any(state['features'].values()));self.assertIsNone(state['domains']['vision'])
        self.assertEqual(marker.stat().st_mode&0o777,0o600)
        # Official 3x-ui normalizes native AWG stream_settings to the empty string.
        with sqlite3.connect(dbpath) as db:
            db.execute('INSERT INTO inbounds VALUES(?,?,?,?,?,?,?)',(777,'amneziawg','0.0.0.0',8443,'','custom','example.com'))
        native=subprocess.run(['bash','-c',code.replace('AWG_RESULT=not_requested','AWG_RESULT=configured'),'fixture',str(dbpath)],capture_output=True,text=True)
        self.assertEqual(native.returncode,0,native.stderr)
        native_state=json.loads(marker.read_bytes())
        self.assertTrue(native_state['features']['amneziawg']);self.assertEqual(native_state['inbound_roles']['amneziawg'],777)
        restored=subprocess.run(['bash','-c',code,'fixture',str(dbpath)],capture_output=True,text=True)
        self.assertEqual(restored.returncode,0,restored.stderr)
        self.assertEqual(marker.read_bytes(),old)
        with sqlite3.connect(dbpath) as db:
            db.execute('ALTER TABLE inbounds DROP COLUMN share_addr_strategy')
            db.execute('ALTER TABLE inbounds DROP COLUMN share_addr')
        legacy=subprocess.run(['bash','-c',code,'fixture',str(dbpath)],capture_output=True,text=True)
        self.assertEqual(legacy.returncode,0,legacy.stderr)
        self.assertEqual(marker.read_bytes(),old)
        fault="python3() { command python3 -c 'import os,sys; os.replace=lambda *a: (_ for _ in ()).throw(OSError(5,\"fixture\")); exec(sys.stdin.read())' \"${@:2}\"; };\n"
        result=subprocess.run(['bash','-c',fault+code,'fixture',str(dbpath)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertEqual(marker.read_bytes(),old)
        self.assertFalse(list(marker.parent.glob('.managed-*')))
        with sqlite3.connect(dbpath) as db:db.execute("UPDATE hosts SET address='other.example' WHERE inbound_id=?",(state['inbound_roles']['ws'],))
        result=subprocess.run(['bash','-c',code,'fixture',str(dbpath)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertEqual(marker.read_bytes(),old)

    def test_managed_state_allows_absent_ws_and_grpc_but_refuses_duplicates(self):
        from test_domains import DomainFixture
        from test_personal_backup import function

        write_state = function('write_managed_state')
        code = write_state + '\n' + '''
CORE_RESULT=configured
PROJECT_SOURCE_SHA=$2
domain=$3
reality_domain=$4
XUIDB=$1
write_managed_state
'''
        for missing in (('ws',), ('grpc',), ('ws', 'grpc')):
            with self.subTest(missing=missing):
                fixture = DomainFixture(self.f.root/('marker-'+'-'.join(missing)))
                db_path = fixture.p(fixture.module.DB)
                marker = fixture.p(fixture.module.MANIFEST)
                original_roles = json.loads(marker.read_text())['inbound_roles']
                fixture.remove_optional_transports(missing)
                marker.unlink()
                command = ['bash', '-c', code, 'fixture', str(db_path), 'a'*40, fixture.panel, fixture.reality]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = {name: iid for name, iid in original_roles.items() if name not in missing}
                saved = marker.read_bytes()
                self.assertEqual(json.loads(saved)['inbound_roles'], expected)
                self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
                for name in {'ws', 'grpc'} & expected.keys():
                    with sqlite3.connect(db_path) as db:
                        db.row_factory = sqlite3.Row
                        duplicate = dict(db.execute('SELECT * FROM inbounds WHERE id=?', (expected[name],)).fetchone())
                        duplicate['id'] = 999
                        db.execute('INSERT INTO inbounds ('+','.join(duplicate)+') VALUES ('+
                                   ','.join('?' for _ in duplicate)+')', tuple(duplicate.values()))
                    result = subprocess.run(command, capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('Ambiguous installed role: '+name, result.stderr)
                    self.assertEqual(marker.read_bytes(), saved)

    def test_compatible_backup_helper_is_refreshed_from_selected_source(self):
        from test_personal_backup import function, relocated
        lock=self.lock_script('acquire_stack_lock || exit $?')
        helpers='\n'.join(relocated(function(n),self.f.root) for n in
                         ('backup_helper_path_safe','backup_helper_compatible','install_backup_tool','prepare_backup_helper'))
        candidate=self.f.script
        old=self.f.path('/usr/local/bin/x-ui-backup')
        old.parent.mkdir(parents=True,exist_ok=True)
        old.write_bytes(candidate.read_bytes()+b'\n# older compatible helper\n')
        old.chmod(0o755)
        self.assertNotEqual(old.read_bytes(),candidate.read_bytes())
        setup=('ui_text() { printf "%s" "$1"; }; msg_err() { echo "$*" >&2; }; msg_warn() { echo "$*" >&2; }; '
               'pin_project_source() { PROJECT_SOURCE_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; '
               'PROJECT_REF=$PROJECT_SOURCE_SHA; GITHUB_RAW=https://source.invalid/$PROJECT_SOURCE_SHA; }; '
               'curl() { command cp "$SOURCE_HELPER" "${@: -1}"; };')
        result=subprocess.run(['bash','-c',lock+'\n'+helpers+'\n'+setup+'\nprepare_backup_helper'],
                              capture_output=True,text=True,env={**os.environ,'SOURCE_HELPER':str(candidate)})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(old.read_bytes(),candidate.read_bytes(),
                         'Compatible but outdated helper was not refreshed')

    def test_legacy_helper_upgrade_offline_reuse_download_and_replace_failure(self):
        from test_personal_backup import function, relocated
        # Keep the real /proc view in the common lock routine.
        lock=self.lock_script('acquire_stack_lock || exit $?')
        helpers='\n'.join(relocated(function(n),self.f.root) for n in
                         ('backup_helper_path_safe','backup_helper_compatible','install_backup_tool','prepare_backup_helper'))
        old=self.f.path('/usr/local/bin/x-ui-backup');old.parent.mkdir(parents=True,exist_ok=True)
        old.write_text('#!/bin/bash\nexit 0\n');old.chmod(0o755);original=old.read_bytes()
        # Candidate is the actual relocated utility, not a mocked capability string.
        candidate=self.f.script
        setup='ui_text() { printf "%s" "$1"; }; msg_err() { echo "$*" >&2; }; msg_warn() { echo "$*" >&2; }; pin_project_source() { GITHUB_RAW=https://source.invalid/exact; };\n'
        def invoke(extra):
            return subprocess.run(['bash','-c',lock+'\n'+helpers+'\n'+setup+extra+'\nprepare_backup_helper'],capture_output=True,text=True)
        failed=invoke('curl() { return 22; };')
        self.assertNotEqual(failed.returncode,0);self.assertEqual(old.read_bytes(),original)
        download='curl() { command cp "'+str(candidate)+'" "${@: -1}"; };'
        failed=invoke(download+'\nmv() { return 1; };')
        self.assertNotEqual(failed.returncode,0);self.assertEqual(old.read_bytes(),original)
        result=invoke(download)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(old.read_bytes(),candidate.read_bytes())
        # No needless replacement when the downloaded helper is unchanged.
        result=invoke(download+'\nmv() { echo UNEXPECTED_REPLACE >&2; return 1; };')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('UNEXPECTED_REPLACE',result.stderr)
        # Offline emergency Restore/Backup can use the already compatible helper.
        result=invoke('curl() { return 22; };')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('installed compatible version',result.stderr)
        result=invoke('pin_project_source() { return 69; }; curl() { echo UNEXPECTED_DOWNLOAD >&2; return 22; };')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('UNEXPECTED_DOWNLOAD',result.stderr)
        # A source-verification mismatch is not treated as an offline condition.
        result=invoke('pin_project_source() { return 1; }; curl() { echo UNEXPECTED_DOWNLOAD >&2; return 22; };')
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('UNEXPECTED_DOWNLOAD',result.stderr)
        bad=self.f.root/'invalid-helper';bad.write_text('#!/bin/bash\nif malformed\n')
        result=invoke('curl() { command cp "'+str(bad)+'" "${@: -1}"; };')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(old.read_bytes(),candidate.read_bytes())
        # A failed replacement is not hidden by the installed helper.
        old.write_bytes(candidate.read_bytes()+b'\n# stale revision\n')
        stale=old.read_bytes()
        result=invoke(download+'\nmv() { return 1; };')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(old.read_bytes(),stale)

    def test_legacy_running_peer_and_unsafe_lock_target(self):
        script=self.f.root/'x-ui-backup';ready=self.f.root/'ready'
        script.write_text(': > "$2"; read -r done\n')
        peer=subprocess.Popen(['bash',str(script),'backup',str(ready)],stdin=subprocess.PIPE)
        try:
            deadline=time.monotonic()+3
            while not ready.exists() and time.monotonic()<deadline:time.sleep(.01)
            result=self.f.run_tool('lock-check');self.assertEqual(result.returncode,75,result.stderr)
        finally:peer.communicate(b'\n',timeout=3)
        path=self.f.root/'run/3x-ui-auto-nginx/operation.lock';path.unlink()
        foreign=self.f.root/'foreign';foreign.write_text('untouched')
        path.symlink_to(foreign)
        result=self.f.run_tool('lock-check');self.assertNotEqual(result.returncode,0)
        self.assertEqual(foreign.read_text(),'untouched');self.assertTrue(path.is_symlink())
