import gettext


#: Version information (major, minor, revision[, 'dev']).
version_info = (2, 0, 2)
#: Version string 'major.minor.revision'.
version = __version__ = ".".join(map(str, version_info))
gettext.install('stalkeragent')
