Name:           bat2sh
Version:        %{ver}
Release:        1%{?dist}
Summary:        Windows batch/PowerShell to Bash script converter

License:        AGPL-3.0-or-later
URL:            https://github.com/yaxiaiyuting/bat2sh
BuildArch:      noarch
Requires:       python3 >= 3.12
Recommends:     python3-pyside6

%global bat2shlib %{_prefix}/lib/bat2sh

%description
bat2sh statically translates Windows batch (.bat/.cmd) and PowerShell (.ps1)
scripts into Bash scripts. It ships both a PySide6 GUI and a CLI.

The conversion core uses only the Python standard library, so the CLI runs
without PySide6; the GUI requires python3-pyside6 (see Recommends).

Output is positioned as an "advanced draft": statements that cannot be
converted automatically are explicitly marked with # TODO rather than
silently producing suspicious scripts.

%install
rm -rf %{buildroot}
install -d %{buildroot}%{_bindir}
install -d %{buildroot}%{bat2shlib}
install -d %{buildroot}%{_datadir}/applications
install -d %{buildroot}%{_datadir}/mime/packages
install -d %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
install -d %{buildroot}%{_datadir}/doc/bat2sh/examples

cp -a %{repo}/python/bat2sh %{buildroot}%{bat2shlib}/
find %{buildroot}%{bat2shlib} -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find %{buildroot}%{bat2shlib} -name '*.pyc' -delete 2>/dev/null || true

install -Dm755 %{repo}/scripts/bat2sh-launcher       %{buildroot}%{_bindir}/bat2sh
install -Dm644 %{repo}/bat2sh.desktop                %{buildroot}%{_datadir}/applications/bat2sh.desktop
install -Dm644 %{repo}/data/mime/bat2sh.xml          %{buildroot}%{_datadir}/mime/packages/bat2sh.xml
install -Dm644 %{repo}/python/bat2sh/data/bat2sh.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/bat2sh.svg
install -Dm644 %{repo}/README.md                     %{buildroot}%{_datadir}/doc/bat2sh/README.md
install -Dm644 %{repo}/LICENSE                       %{buildroot}%{_datadir}/doc/bat2sh/LICENSE
cp -a %{repo}/examples/. %{buildroot}%{_datadir}/doc/bat2sh/examples/

%post
if [ -x /usr/bin/update-mime-database ]; then
    update-mime-database %{_datadir}/mime &> /dev/null || :
fi
if [ -x /usr/bin/update-desktop-database ]; then
    update-desktop-database %{_datadir}/applications &> /dev/null || :
fi

%postun
if [ -x /usr/bin/update-mime-database ]; then
    update-mime-database %{_datadir}/mime &> /dev/null || :
fi
if [ -x /usr/bin/update-desktop-database ]; then
    update-desktop-database %{_datadir}/applications &> /dev/null || :
fi

%files
%license %{_datadir}/doc/bat2sh/LICENSE
%{_bindir}/bat2sh
%{bat2shlib}/bat2sh
%{_datadir}/applications/bat2sh.desktop
%{_datadir}/mime/packages/bat2sh.xml
%{_datadir}/icons/hicolor/scalable/apps/bat2sh.svg
%{_datadir}/doc/bat2sh/README.md
%{_datadir}/doc/bat2sh/examples

%changelog
* Sun Sep 20 2026 yaxiaiyuting <jiangtianyou189@qq.com> - %{ver}-1
- Initial RPM packaging for bat2sh %{ver}
