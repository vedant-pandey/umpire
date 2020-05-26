import argparse # For parsing CLI arguments
import configparser # For parsing configuration file formats
import collections
import hashlib
import os
import re
import sys
import zlib

argparser = argparse.ArgumentParser(description="Umpire version control manager")
argsubparsers = argparser.add_subparsers(title="Commands", dest="command")
argsubparsers.required = True

# CLI argument parser for init command
argsp = argsubparsers.add_parser("init", help="Initialize a new, empty repository.")
argsp.add_argument(
	"path", 
	metavar="directory",
	nargs="?", 
	default=".", 
	help="Where to create he repository"
)

def main(argv=sys.argv[1:]):
	args = argparser.parse_args(argv)

	if   args.command == "add"         : cmd_add(args)
	elif args.command == "cat-file"    : cmd_cat_file(args)
	elif args.command == "checkout"    : cmd_checkout(args)
	elif args.command == "commit"      : cmd_commit(args)
	elif args.command == "hash-object" : cmd_hash_object(args)
	elif args.command == "init"        : cmd_init(args)
	elif args.command == "log"         : cmd_log(args)
	elif args.command == "ls-tree"     : cmd_ls_tree(args)
	elif args.command == "merge"       : cmd_merge(args)
	elif args.command == "rebase"      : cmd_rebase(args)
	elif args.command == "rev-parse"   : cmd_rev_parse(args)
	elif args.command == "rm"          : cmd_rm(args)
	elif args.command == "show-ref"    : cmd_show_ref(args)
	elif args.command == "tag"         : cmd_tag(args)

class UmpRepo(object):
	"""An umpire repository"""

	worktree = None
	umpDir = None
	conf = None

	def __init__(self, path, force=False):
		self.worktree = path
		self.umpDir = os.path.join(path, ".ump")

		if not (force or os.path.isdir(self.umpDir)):
			raise Exception("Not a working umpire repository %s" % path)

		# Read config file
		self.conf = configparser.ConfigParser()
		cf = repo_file(self, "config")

		if cf and os.path.exists(cf):
			self.conf.read([cf])
		elif not force:
			raise Exception("Configuration file not present")

		if not force:
			vers = int(self.conf.get("core", "repositoryformatversion"))
			if vers != 0:
				raise Exception("Unsupported repository format version %s" % vers)



def repo_path(repo, *path):
	return os.path.join(repo.umpDir, *path)

def repo_file(repo, *path, mkdir=False):
	"""Same as repo_path, but create dirname(*path) if absent. For example
	repo_file(r, 'refs', 'remotes', 'origin', 'HEAD') will create
	.ump/refs/remotes/origin """

	if repo_dir(repo, *path[:-1], mkdir=mkdir):
		return repo_path(repo, *path)

def repo_dir(repo, *path, mkdir=False):
	"""Same as repo_path, but mkdir *path if absent and mkdir is True"""

	path = repo_path(repo, *path)

	if os.path.exists(path):
		if os.path.isdir(path):
			return path
		else:
			raise Exception("Not a working umpire repository %s" % path)

	if mkdir:
		os.makedirs(path)
		return path
	else:
		return None

def repo_create(path):
	"""Initialize a new repository at path."""

	repo = UmpRepo(path, True)

	# Check the paths don't already exist

	if os.path.exists(repo.worktree):
		if not os.path.isdir(repo.worktree):
			raise Exception("%s is not a directory" % path)

		if os.listdir(repo.worktree):
			raise Exception("%s is not empty" % path)

	else:
		os.makedirs(repo.worktree)

	assert(repo_dir(repo, "branches", mkdir=True))
	assert(repo_dir(repo, "objects", mkdir=True))
	assert(repo_dir(repo, "refs", "tags", mkdir=True))
	assert(repo_dir(repo, "refs", "heads", mkdir=True))

	# Description file
	with open(repo_file(repo, "description"), "w") as f:
		f.write("Unnamed repository, edit this file 'description' to name the repository.\n")

	# HEAD
	with open(repo_file(repo, "HEAD"), "w") as f:
		f.write("ref: refs/heads/master\n")

	with open(repo_file(repo, "config"), "w") as f:
		config = repo_default_config()
		config.write(f)

	return repo

def repo_default_config():
	ret = configparser.ConfigParser()

	ret.add_section("core")
	ret.set("core", "repositoryformatversion", "0")
	ret.set("core", "filemode", "false")
	ret.set("core", "bare", "false")

	return ret


# Init command handler
def cmd_init(args):
	repo_create(args.path)

def repo_find(path=".", required=True):
	path = os.path.realpath(path)

	if os.path.isdir(os.path.join(path, ".ump")):
		return UmpRepo(path)

	# Recurse parent if current directory is not the main git directory
	parent = os.path.realpath(os.path.join(path, ".."))

	# Base case if current directory is system root
	if parent == path:
		if required:
			raise Exception("No upmire repository found")
		else:
			return None

	return repo_find(parent, required)