# Maintainer: yaxiaiyuting <jiangtianyou189@qq.com>
pkgname=bat2sh
pkgver=1.4.2
pkgrel=1
pkgdesc="将 Windows 批处理 (.bat/.cmd) 与 PowerShell (.ps1) 脚本转换为 Bash 脚本的图形化工具"
arch=('any')
url="https://github.com/yaxiaiyuting/bat2sh"
license=('AGPL-3.0-or-later')
depends=('python' 'pyside6' 'hicolor-icon-theme' 'shared-mime-info' 'desktop-file-utils')
makedepends=()
install=bat2sh.install
options=('!strip')
source=("$pkgname-$pkgver.tar.gz::$url/archive/refs/tags/v$pkgver.tar.gz")
sha256sums=('83ec69261e29c38f624387213b1c0ba1b80d3bab403c1333fc8cdfb44a5b84e0')

package() {
  cd "${srcdir}/${pkgname}-${pkgver}"

  install -d "${pkgdir}/usr/lib/${pkgname}"
  cp -a python/bat2sh "${pkgdir}/usr/lib/${pkgname}/"

  install -Dm755 scripts/bat2sh-launcher "${pkgdir}/usr/bin/${pkgname}"
  install -Dm644 bat2sh.desktop "${pkgdir}/usr/share/applications/${pkgname}.desktop"
  install -Dm644 data/mime/bat2sh.xml \
    "${pkgdir}/usr/share/mime/packages/${pkgname}.xml"
  install -Dm644 python/bat2sh/data/bat2sh.svg \
    "${pkgdir}/usr/share/icons/hicolor/scalable/apps/${pkgname}.svg"
  install -Dm644 LICENSE "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE"
  install -Dm644 README.md "${pkgdir}/usr/share/doc/${pkgname}/README.md"

  install -d "${pkgdir}/usr/share/doc/${pkgname}/examples"
  cp -a examples/. "${pkgdir}/usr/share/doc/${pkgname}/examples/"
}
