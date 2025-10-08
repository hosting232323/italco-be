{pkgs}: {
  deps = [
    pkgs.postgresql
    pkgs.pkg-config
    pkgs.cairo
    pkgs.python3
    pkgs.python3Packages.pip
  ];
}
