# Maintainer: yaxiaiyuting <jiangtianyou189@qq.com>
pkgname=bat2sh
pkgver=2.11.1
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
sha256sums=('c8955ad3dec6d4574dc18060e8543bf2d2c45f6664e2d4fdb85c74e83d4016ee')

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
  # NOTICE 持有版权人与应用声明（LICENSE 为纯 AGPL-3.0 官方正文），两者应同装。
  #
  # ⚠️ 必须做存在性判断，不要「清理」成无条件 install：
  #    PKGBUILD 是从 **tag tarball** 构建的（见 source= 行），而 NOTICE 是在
  #    v2.9.0 **之后**才加入仓库的 —— v2.9.0 及更早的 tarball 里没有该文件，
  #    无条件 install 会让 `makepkg -si` 直接失败（实测复现过）。
  #    下一次版本 bump（tag tarball 含 NOTICE 后）本判断自然恒真，可保留亦无害。
  if [[ -f NOTICE ]]; then
    install -Dm644 NOTICE "${pkgdir}/usr/share/licenses/${pkgname}/NOTICE"
  fi
  install -Dm644 README.md "${pkgdir}/usr/share/doc/${pkgname}/README.md"

  install -d "${pkgdir}/usr/share/doc/${pkgname}/examples"
  cp -a examples/. "${pkgdir}/usr/share/doc/${pkgname}/examples/"
}
