"""Actual entrypoint/TTY acceptance and private Backup management contracts."""
import itertools
import json
import os
from pathlib import Path
import pty
import re
import select
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


class Manager(unittest.TestCase):
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

    def test_real_entrypoint_tty_exit_back_invalid_and_no_tty(self):
        for answers in (b'1\n0\n',b'1\n9\n3\n0\n0\n'):
            code,text=tty_run(ROOT/'x-ui-latest.sh',answers)
            self.assertEqual(code,0,text)
            self.assertIn('1. Installation',text)
            self.assertIn('3. Backups',text)
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
            for args in (('-install','y'),('-version','v3.11.0'),('-uninstall','y'),('-unknown','value')):
                result=subprocess.run(['bash',str(script),*args],input='2\n',capture_output=True,text=True,
                                      env={**os.environ,'UI_LANG':'ru'})
                self.assertEqual(result.returncode,37,result.stderr)
                self.assertEqual(result.stdout,'CLI:en|'+''.join('<'+arg+'>' for arg in args))
                self.assertNotIn('Select language',result.stdout)

    def test_russian_install_questions_defaults_and_eof(self):
        library='source "'+str(ROOT/'x-ui-latest.sh')+'"\nUI_LANG=ru\n'
        with tempfile.TemporaryDirectory() as temporary:
            script=Path(temporary)/'questions.sh'
            script.write_text(library+'''
validate_domains && select_security && select_vision && select_amneziawg && select_adguard && select_client || exit $?
printf 'FLAGS:%s:%s:%s:%s:%s:%s:%s:%s\n' "$INSTALL_SECURITY" "$INSTALL_VISION" "$INSTALL_AWG" "$INSTALL_AGH" "$CREATE_CLIENT" "$domain" "$reality_domain" "$vision_domain"
''')
            code,text=tty_run(script,b'Panel.Example\nReality.Example\n\ny\nVision.Example\ny\ny\n\n')
            self.assertEqual(code,0,text)
            for prompt in ('домен панели 3X-UI','домен VLESS REALITY','Усилить безопасность VPS? [Y/n]',
                           'дополнительное подключение VLESS TCP/TLS','домен VLESS TLS Vision',
                           'дополнительное подключение AmneziaWG? [y/N]','Установить и настроить AdGuard Home? [y/N]',
                           'Создать клиента в 3X-UI'):
                self.assertIn(prompt,text)
            self.assertIn('FLAGS:y:y:y:y:y:panel.example:reality.example:vision.example',text)
            for name,variable,default in (('select_security','INSTALL_SECURITY','y'),('select_vision','INSTALL_VISION','n'),
                    ('select_amneziawg','INSTALL_AWG','n'),('select_adguard','INSTALL_AGH','n'),('select_client','CREATE_CLIENT','y')):
                for answers,expected in ((b'\n',default),(b'bad\nn\n','n'),(b'\x04','n')):
                    with self.subTest(question=name,answers=answers):
                        script.write_text(library+name+'; printf "RESULT:%s\\n" "$'+variable+'"\n')
                        code,text=tty_run(script,answers)
                        self.assertEqual(code,0,text);self.assertIn('RESULT:'+expected,text)
                        if answers.startswith(b'bad'):self.assertIn('Введите y или n.',text)

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


class ManagerBackup(unittest.TestCase):
    def setUp(self):
        from test_personal_backup import PersonalBackup
        self.f=PersonalBackup('runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)

    def test_russian_backup_restore_confirmation_status_and_partial_messages(self):
        from test_personal_backup import relocated
        root=self.f.root;helper=self.f.path('/usr/local/bin/x-ui-backup')
        helper.parent.mkdir(parents=True,exist_ok=True)
        helper.write_text('''#!/bin/bash
case "$1" in
    inspect) printf '{"format_version":3}\\n' ;;
    backup) printf '{"status":"success","archive":"%s/var/backups/x-ui/fixture.tar.gz"}\\n' "$FIXTURE_ROOT" ;;
    restore) printf restored > "$FIXTURE_ROOT/restored"; exit "${RESTORE_EXIT:-0}" ;;
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
                self.assertEqual(self.f.path('/etc/x-ui/x-ui.db').read_bytes(),original)
                if not restored and '\x04' not in answers:self.assertIn('Отменено.',text)
                if flags.get('RESTORE_EXIT'):
                    self.assertIn('Restore: FAILED (exit 42)',text);self.assertNotIn('Restore: SUCCESS',text)
                elif restored:
                    self.assertIn('Restore: SUCCESS',text)
                    self.assertIn('Overall: PARTIAL' if expected else 'Overall: SUCCESS',text)
                    self.assertEqual(text.count('1. Установка'),1,text)
                    if expected:self.assertIn('данные сохранены, но настройка Security не завершена',text)

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
            return 'source \"'+str(copy)+'\"; check_os() { :; }; check_cpu() { :; }; initialize_installation() { :; }; ip() { echo \"src 127.0.0.1\"; }; confirm_destructive_reinstall() { :; }; main() { '+action+'; }; uninstall_xui() { '+action+'; }; run_installation '+('-uninstall y' if operation=='uninstall' else '-install y')
        for first,second in itertools.product(('backup','restore','install','uninstall','domains'),repeat=2):
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
                db.execute('INSERT INTO hosts VALUES(?,?,443)',(iid,'example.com'))
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
        setup='msg_err() { echo "$*" >&2; }; pin_project_source() { GITHUB_RAW=https://source.invalid/exact; };\n'
        def invoke(extra):
            return subprocess.run(['bash','-c',lock+'\n'+helpers+'\n'+setup+extra+'\nprepare_backup_helper'],capture_output=True,text=True)
        failed=invoke('curl() { return 22; };')
        self.assertNotEqual(failed.returncode,0);self.assertEqual(old.read_bytes(),original)
        download='curl() { command cp "'+str(candidate)+'" "${@: -1}"; };'
        failed=invoke(download+'\nmv() { return 1; };')
        self.assertNotEqual(failed.returncode,0);self.assertEqual(old.read_bytes(),original)
        result=invoke(download)
        self.assertEqual(result.returncode,0,result.stderr)
        result=invoke('curl() { echo UNEXPECTED_DOWNLOAD >&2; return 22; }; pin_project_source() { return 9; };')
        self.assertEqual(result.returncode,0,result.stderr);self.assertNotIn('UNEXPECTED_DOWNLOAD',result.stderr)

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
