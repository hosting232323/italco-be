{ pkgs }:
{
  deps = [
    pkgs.postgresql
    pkgs.pkg-config
    pkgs.cairo
    pkgs.python3
    pkgs.python3Packages.pip
    pkgs.python3Packages.setuptools
    pkgs.python3Packages.wheel
    pkgs.gcc
    pkgs.gobject-introspection
    pkgs.glib
  ];
}
