# Maintainer: yaxiaiyuting <jiangtianyou189@qq.com>
pkgname=bat2sh
pkgver=1.0.1
pkgrel=1
pkgdesc="将 Windows 批处理 (.bat/.cmd) 与 PowerShell (.ps1) 脚本转换为 Bash 脚本的图形化工具"
arch=('any')
url="https://github.com/yaxiaiyuting/bat2sh"
license=('AGPL-3.0-or-later')
depends=('python' 'pyside6' 'hicolor-icon-theme')
makedepends=()
options=('!strip')
source=("$pkgname-$pkgver.tar.gz::$url/archive/refs/tags/v$pkgver.tar.gz")
sha256sums=('07ab51860d6eba24e324833b531a12a290cb42afdaed4e4cd91c12657bda0a11')

package() {
  cd "${srcdir}/${pkgname}-${pkgver}"

  install -d "${pkgdir}/usr/lib/${pkgname}"
  cp -a python/bat2sh "${pkgdir}/usr/lib/${pkgname}/"

  install -Dm755 scripts/bat2sh-launcher "${pkgdir}/usr/bin/${pkgname}"
  install -Dm644 bat2sh.desktop "${pkgdir}/usr/share/applications/${pkgname}.desktop"
  install -Dm644 python/bat2sh/data/bat2sh.svg \
    "${pkgdir}/usr/share/icons/hicolor/scalable/apps/${pkgname}.svg"
  install -Dm644 LICENSE "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE"
  install -Dm644 README.md "${pkgdir}/usr/share/doc/${pkgname}/README.md"

  install -d "${pkgdir}/usr/share/doc/${pkgname}/examples"
  cp -a examples/. "${pkgdir}/usr/share/doc/${pkgname}/examples/"
}
