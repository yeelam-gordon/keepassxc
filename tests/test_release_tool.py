#!/usr/bin/env python3

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest import mock
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('release_tool', ROOT / 'release-tool.py')
release_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_tool)


def find_cmake():
    executable = shutil.which('cmake')
    if executable:
        return executable
    if os.name == 'nt':
        visual_studio = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Microsoft Visual Studio'
        matches = sorted(visual_studio.glob(
            r'*\*\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'))
        if matches:
            return str(matches[-1])
    raise RuntimeError('CMake is required for deployqt resolution tests.')


class TestPrerequisites(unittest.TestCase):
    def test_basic_checks_do_not_require_gnupg(self):
        with mock.patch.object(release_tool.Check, 'check_src_dir_exists'), \
                mock.patch.object(release_tool.Check, 'check_git'), \
                mock.patch.object(release_tool.Check, 'check_git_repository'), \
                mock.patch.object(release_tool.Check, 'check_xcode_setup'), \
                mock.patch.object(release_tool.Check, 'check_gnupg',
                                  side_effect=AssertionError('unexpected GnuPG check')):
            release_tool.Check.perform_basic_checks('.')

    def test_tag_requires_gnupg(self):
        parser = mock.Mock()
        with mock.patch.object(release_tool.Check, 'perform_basic_checks'), \
                mock.patch.object(release_tool.Check, 'perform_version_checks', return_value='release/2.8.x'), \
                mock.patch.object(release_tool.Check, 'check_gnupg',
                                  side_effect=release_tool.Error('GnuPG not installed.')):
            with self.assertRaisesRegex(release_tool.Error, 'GnuPG not installed'):
                release_tool.Tag(parser).run(
                    version='2.8.0',
                    src_dir='.',
                    release_branch=None,
                    tag_name=None,
                    no_latest=False,
                    sign_key=None,
                    no_sign=False,
                    yes=True,
                    skip_translations=True,
                    tx_resource=None,
                    tx_min_perc=0)

    def test_gpg_sign_requires_gnupg(self):
        with mock.patch.object(release_tool.Check, 'check_gnupg',
                               side_effect=release_tool.Error('GnuPG not installed.')):
            with self.assertRaisesRegex(release_tool.Error, 'GnuPG not installed'):
                release_tool.GPGSign(mock.Mock()).run(file=['missing'], gpg_key=None)


class TestWindowsTriplets(unittest.TestCase):
    def test_builtin_target_and_x64_host(self):
        self.assertEqual(
            ('arm64-windows', 'x64-windows'),
            release_tool._windows_vcpkg_triplets('arm64', False, 'AMD64'))

    def test_release_target_and_arm64_host(self):
        self.assertEqual(
            ('arm64-windows-release', 'arm64-windows'),
            release_tool._windows_vcpkg_triplets('arm64', True, 'aarch64'))

    def test_x64_release_target(self):
        self.assertEqual(
            ('x64-windows-release', 'x64-windows'),
            release_tool._windows_vcpkg_triplets('amd64', True, 'x86_64'))

    def test_unknown_host_fails_closed(self):
        with self.assertRaisesRegex(release_tool.Error, 'OS=.*processor=riscv64'):
            release_tool._windows_vcpkg_triplets('amd64', True, 'riscv64')

    def test_cmake_triplet_override_detection(self):
        self.assertTrue(release_tool._cmake_option_is_set(
            ['-DVCPKG_TARGET_TRIPLET:STRING=custom-triplet'], 'VCPKG_TARGET_TRIPLET'))
        self.assertFalse(release_tool._cmake_option_is_set(
            ['-DVCPKG_HOST_TRIPLET=x64-windows'], 'VCPKG_TARGET_TRIPLET'))

    def test_user_triplet_overrides_are_preserved(self):
        options = [
            '-DVCPKG_TARGET_TRIPLET=custom-target',
            '-DVCPKG_HOST_TRIPLET=custom-host',
        ]
        release_tool._add_windows_vcpkg_triplets(options, 'arm64', True, 'AMD64')
        self.assertEqual(2, len(options))

    def test_missing_triplet_options_are_added(self):
        options = []
        release_tool._add_windows_vcpkg_triplets(options, 'amd64', True, 'ARM64')
        self.assertEqual([
            '-DVCPKG_TARGET_TRIPLET=x64-windows-release',
            '-DVCPKG_HOST_TRIPLET=arm64-windows',
        ], options)

    def test_runner_vcpkg_installation_root_is_supported(self):
        with mock.patch.object(release_tool.shutil, 'which', return_value=None), \
                mock.patch.dict(release_tool.os.environ,
                                {'VCPKG_INSTALLATION_ROOT': str(ROOT / 'runner-vcpkg')},
                                clear=True), \
                mock.patch.object(Path, 'is_file', return_value=True):
            toolchain = release_tool.Build._get_vcpkg_toolchain_file()
        self.assertEqual(
            (ROOT / 'runner-vcpkg' / 'scripts' / 'buildsystems' / 'vcpkg.cmake').resolve(),
            toolchain)


class TestQtManifest(unittest.TestCase):
    def test_windeployqt_is_windows_only(self):
        manifest = json.loads((ROOT / 'vcpkg.json').read_text(encoding='utf-8'))
        qt_dependencies = manifest['features']['qt']['dependencies']
        windeployqt = [
            dependency for dependency in qt_dependencies
            if isinstance(dependency, dict) and 'windeployqt' in dependency.get('features', [])
        ]
        self.assertEqual(1, len(windeployqt))
        self.assertEqual('windows', windeployqt[0]['platform'])

    def test_release_triplets_are_windows_only(self):
        triplets = ROOT / 'vcpkg' / 'triplets'
        for architecture in ('x64', 'arm64'):
            text = (triplets / f'{architecture}-windows-release.cmake').read_text(encoding='utf-8')
            self.assertIn(f'set(VCPKG_TARGET_ARCHITECTURE {architecture})', text)
            self.assertIn('set(VCPKG_BUILD_TYPE release)', text)

    def test_deployqt_host_mapping_is_os_scoped(self):
        cmake = (ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
        self.assertIn('kpxc_resolve_vcpkg_deployqt(', cmake)
        self.assertIn('get_filename_component(DEPLOYQT_WORKING_DIR', cmake)
        self.assertNotIn('configure_file("${_deployqt_source}"', cmake)

    def test_windows_deployqt_uses_host_tool_working_directory(self):
        cmake = (ROOT / 'src' / 'CMakeLists.txt').read_text(encoding='utf-8')
        self.assertIn('WORKING_DIRECTORY "${DEPLOYQT_WORKING_DIR}")', cmake)
        self.assertIn('WORKING_DIRECTORY \\"${DEPLOYQT_WORKING_DIR}\\"', cmake)
        self.assertIn('--dir \\"\\${CMAKE_INSTALL_PREFIX}\\"', cmake)
        self.assertIn('\\"\\${CMAKE_INSTALL_PREFIX}/${PROGNAME}.exe\\"', cmake)

    def test_gui_target_avoids_duplicate_app_local_deployment(self):
        cmake = (ROOT / 'src' / 'CMakeLists.txt').read_text(encoding='utf-8')
        disable = cmake.index('set(VCPKG_APPLOCAL_DEPS OFF)')
        executable = cmake.index('add_executable(${PROGNAME} main.cpp)')
        restore = cmake.index('set(VCPKG_APPLOCAL_DEPS ON)', executable)
        self.assertLess(disable, executable)
        self.assertLess(executable, restore)

    def test_vcpkg_qt_install_deployment_is_ordered(self):
        release_tool = (ROOT / 'release-tool.py').read_text(encoding='utf-8')
        self.assertIn("app_local_install = 'OFF' if build_qt else 'ON'", release_tool)
        cmake = (ROOT / 'src' / 'CMakeLists.txt').read_text(encoding='utf-8')
        deployqt = cmake.index('COMMAND ${DEPLOYQT_EXE} ${DEPLOYQT_ARGS}')
        condition = cmake.index('if(WITH_BUILD_QT)', deployqt)
        applocal = cmake.index('\\"${Z_VCPKG_EXECUTABLE}\\" z-applocal')
        self.assertLess(deployqt, applocal)
        self.assertLess(condition, applocal)
        self.assertNotIn('if(${WITH_BUILD_QT})', cmake)

    def test_deployqt_x64_host_arm64_target(self):
        subprocess.run([
            find_cmake(),
            '-DTEST_CASE=windows-x64-to-arm64',
            '-P',
            str(ROOT / 'tests' / 'cmake' / 'test_deployqt_resolution.cmake'),
        ], check=True, cwd=ROOT)

    def test_deployqt_native_windows_target(self):
        subprocess.run([
            find_cmake(),
            '-DTEST_CASE=windows-native-x64',
            '-P',
            str(ROOT / 'tests' / 'cmake' / 'test_deployqt_resolution.cmake'),
        ], check=True, cwd=ROOT)

    def test_deployqt_macos_cross_target(self):
        subprocess.run([
            find_cmake(),
            '-DTEST_CASE=macos-x64-to-arm64',
            '-P',
            str(ROOT / 'tests' / 'cmake' / 'test_deployqt_resolution.cmake'),
        ], check=True, cwd=ROOT)
        helper = (ROOT / 'cmake' / 'KPXCMacDeployHelpers.cmake').read_text(encoding='utf-8')
        command_start = helper.index('set(COMMAND_ARGS')
        command = helper[command_start:helper.index('install(CODE', command_start)]
        self.assertLess(command.index('${APP_BUNDLE_PATH}'), command.index('${DEPLOYQT_ARGS}'))

    def test_qrencode_release_only_library(self):
        subprocess.run([
            find_cmake(),
            '-P',
            str(ROOT / 'tests' / 'cmake' / 'test_find_qrencode.cmake'),
        ], check=True, cwd=ROOT)


class TestValidationScripts(unittest.TestCase):
    def test_uninstall_requires_install_path_removal(self):
        script = (ROOT / '.github' / 'scripts' / 'verify-windows-package.ps1').read_text(
            encoding='utf-8')
        self.assertIn(
            'if (Test-Path -LiteralPath $installRoot) {\n'
            '        throw "MSI install path was not removed after uninstall: $installRoot"\n'
            '    }',
            script)

    def test_msi_metadata_query_does_not_leak_com_output(self):
        script = (ROOT / '.github' / 'scripts' / 'verify-windows-package.ps1').read_text(
            encoding='utf-8')
        self.assertIn('[void] $view.Execute()', script)

    def test_only_matching_vc_redist_allows_x86_bootstrapper(self):
        script = (ROOT / '.github' / 'scripts' / 'verify-windows-package.ps1').read_text(
            encoding='utf-8')
        self.assertIn('$expectedRedist = "vc_redist.$Architecture.exe"', script)
        self.assertIn('$file.Name -ieq $expectedRedist -and $actual -eq 0x014C', script)

    def test_build_records_and_enforces_minimum_free_space(self):
        script = (ROOT / '.github' / 'scripts' / 'invoke-release-build.ps1').read_text(
            encoding='utf-8')
        self.assertIn('while (-not $process.WaitForExit($DiskPollSeconds * 1000))', script)
        self.assertIn('disk.minimum_free_gib=$minimumFreeGiB', script)
        self.assertIn('if ($sampleFreeGiB -lt $MinimumFinalFreeGiB)', script)
        self.assertIn('$process.Kill($true)', script)


class TestBuildTestSelection(unittest.TestCase):
    def test_database_test_runs_in_serial_group(self):
        release_tool = (ROOT / 'release-tool.py').read_text(encoding='utf-8')
        self.assertIn("serial_tests = 'gui|cli|database'", release_tool)
        self.assertIn("[ctest_cmd, '-E', serial_tests", release_tool)
        self.assertIn("[ctest_cmd, '-R', serial_tests", release_tool)
        self.assertIn("'--timeout', '120', '-V'", release_tool)

    def test_vcpkg_qt_plugins_are_available_to_windows_tests(self):
        tests_cmake = (ROOT / 'tests' / 'CMakeLists.txt').read_text(encoding='utf-8')
        self.assertIn('if(WIN32 AND WITH_BUILD_QT)', tests_cmake)
        self.assertIn('"QT_PLUGIN_PATH=${Qt6_PREFIX}/Qt6/plugins"', tests_cmake)

    def test_windows_artifacts_support_cross_volume_output(self):
        release_tool = (ROOT / 'release-tool.py').read_text(encoding='utf-8')
        self.assertIn('shutil.move(artifact, output_dir / artifact.name)', release_tool)
        self.assertNotIn('artifact.replace(output_dir / artifact.name)', release_tool)


class TestWindowsPackagingConfiguration(unittest.TestCase):
    def test_cpack_architectures_fail_closed(self):
        cmake = (ROOT / 'src' / 'CMakeLists.txt').read_text(encoding='utf-8')
        self.assertIn('set(CPACK_WIX_ARCHITECTURE x64)', cmake)
        self.assertIn('set(CPACK_WIX_ARCHITECTURE arm64)', cmake)
        self.assertIn('CMAKE_VERSION VERSION_LESS "3.24"', cmake)
        self.assertIn('Unsupported Windows release architecture', cmake)

    def test_wix_installer_version_is_500(self):
        root = ElementTree.parse(ROOT / 'share' / 'windows' / 'wix-template.xml').getroot()
        namespace = {'wix': 'http://schemas.microsoft.com/wix/2006/wi'}
        package = root.find('.//wix:Package', namespace)
        self.assertEqual('500', package.attrib['InstallerVersion'])


if __name__ == '__main__':
    unittest.main()
