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

def main(argv=sys.argv[1:]):
	args = argparser.parse_args(argv)

	if   args.command == "add"         : cmd_add(args)
	elif args.command == "cat-file"    : cmd_cat_file(args)
	elif args.command == "checkout"    : cmd_checkout(args)
	# elif args.command == "commit"      : cmd_commit(args)
	elif args.command == "hash-object" : cmd_hash_object(args)
	elif args.command == "init"        : cmd_init(args)
	elif args.command == "log"         : cmd_log(args)
	elif args.command == "ls-tree"     : cmd_ls_tree(args)
	# elif args.command == "merge"       : cmd_merge(args)
	# elif args.command == "rebase"      : cmd_rebase(args)
	elif args.command == "rev-parse"   : cmd_rev_parse(args)
	# elif args.command == "rm"          : cmd_rm(args)
	elif args.command == "show-ref"    : cmd_show_ref(args)
	elif args.command == "tag"         : cmd_tag(args)

class GitRepository(object):
	"""An umpire repository"""

	worktree = None
	gitDir = None
	conf = None

	def __init__(self, path, force=False):
		self.worktree = path
		self.gitDir = os.path.join(path, ".git")

		if not (force or os.path.isdir(self.gitDir)):
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
	return os.path.join(repo.gitDir, *path)

def repo_file(repo, *path, mkdir=False):
	"""Same as repo_path, but create dirname(*path) if absent. For example
	repo_file(r, 'refs', 'remotes', 'origin', 'HEAD') will create
	.git/refs/remotes/origin """

	if repo_dir(repo, *path[:-1], mkdir=mkdir):
		return repo_path(repo, *path)

def repo_dir(repo, *path, mkdir=False):
	"""Same as repo_path, but mkdir *path if absent and mkdir is True"""

	path = repo_path(repo, *path)

	if os.path.exists(path):
		if os.path.isdir(path):
			return path
		else:
			raise Exception("Not a working repository %s" % path)

	if mkdir:
		os.makedirs(path)
		return path
	else:
		return None

def repo_create(path):
	"""Initialize a new repository at path."""

	repo = GitRepository(path, True)

	# Check the paths don't already exist

	if os.path.exists(repo.worktree):
		if not os.path.isdir(repo.worktree):
			raise Exception("%s is not a directory" % path)

		if os.listdir(repo.worktree):
			raise Exception("%s is not empty" % os.path.realpath(path))

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

# CLI argument parser for init command
argsp = argsubparsers.add_parser("init", help="Initialize a new, empty repository.")
argsp.add_argument(
	"path", 
	metavar="directory",
	nargs="?", 
	default=".", 
	help="Where to create the repository"
)


# Init command handler
def cmd_init(args):
	repo_create(args.path)

def repo_find(path=".", required=True):
	path = os.path.realpath(path)

	if os.path.isdir(os.path.join(path, ".git")):
		return GitRepository(path)

	# Recurse parent if current directory is not the main umpire directory
	parent = os.path.realpath(os.path.join(path, ".."))

	# Base case if current directory is system root
	if parent == path:
		if required:
			raise Exception("No repository found")
		else:
			return None

	return repo_find(parent, required)

class GitObject(object):
	repo = None

	def __init__(self, repo, data=None):
		self.repo=repo

		if data != None:
			self.deserialize(data)

	def serialize(self):
		"""Abstract function to be implemented by sub classes
		The data class member contains information of the object as byte string"""
		raise Exception("Unimplemented method")

	def deserialize(self, data):
		raise Exception("Unimplemented method")

def object_read(repo, sha):
	"""Read object id from repo and return GitObject"""

	path = repo_file(repo, "objects", sha[0:2], sha[2:])

	with open (path, "rb") as f:
		raw = zlib.decompress(f.read())

		x = raw.find(b' ')
		fmt = raw[0:x]

		y = raw.find(b'\x00', x)
		size = int(raw[x:y].decode("ascii"))
		if size != len(raw) - y - 1:
			raise Exception("Malformed object {0}: bad length".format(sha))

		if fmt == b'commit' : c=GitCommit
		elif fmt == b'tree' : c=GitTree
		elif fmt == b'tag'  : c=GitTag
		elif fmt == b'blob' : c=GitBlob
		else:
			raise Exception("Unknown type %s for object %s".format(fmt.decode("ascii"), sha))

		return c(repo, raw[y + 1:])

# Placeholder function
def object_find(repo, name, fmt=None, follow=True):
	sha = object_resolve(repo, name)

	if not sha:
		raise Exception("No such reference {0}.".format(name))

	if len(sha) > 1:
		raise Exception("Ambiguous reference {0}: Candidates are:\n - {1}.".format(name,  "\n - ".join(sha)))

	sha = sha[0]

	if not fmt:
		return sha

	while True:
		obj = object_read(repo, sha)

		if obj.fmt == fmt:
				return sha

		if not follow:
				return None

		# Follow tags
		if obj.fmt == b'tag':
				sha = obj.kvlm[b'object'].decode("ascii")
		elif obj.fmt == b'commit' and fmt == b'tree':
			sha = obj.kvlm[b'tree'].decode("ascii")
		else:
			return None

def object_write(obj, true_write=True):
	# Serialize data
	data = obj.serialize()

	# Set header
	result = obj.fmt + b' ' + str(len(data)).encode() + b'\x00' + data

	# Compute hash
	sha = hashlib.sha1(result).hexdigest()

	if true_write:
		# Create path
		path = repo_file(obj.repo, "objects", sha[0:2], sha[2:], mkdir=true_write)

		with open(path, "wb") as f:
			f.write(zlib.compress(result))
	
	return sha

class GitBlob(GitObject):
	fmt = b'blob'

	def serialize(self):
		return self.blobdata

	def deserialize(self, data):
		self.blobdata = data

# CLI argument parser for cat-file command
argsp = argsubparsers.add_parser("cat-file", help="Display content of repository objects")

argsp.add_argument(
	"type",
	metavar="type",
	choices=["blob", "commit", "tag", "tree"],
	help="Specify the type"
)

argsp.add_argument(
	"object",
	metavar="object",
	help="Object to be displayed"
)

def cmd_cat_file(args):
	repo = repo_find()
	cat_file(repo, args.object, fmt=args.type.encode())

def cat_file(repo, obj, fmt=None):
	obj = object_read(repo, object_find(repo, obj, fmt=fmt))
	sys.stdout.buffer.write(obj.serialize())

# CLI argument parser for hash-object command
argsp = argsubparsers.add_parser(
	"hash-object",
	help="Compute object ID and optionally creates a blob from a file"
)

argsp.add_argument(
	"-t",
	metavar="type",
	dest="type",
	choices=["blob", "commit", "tag", "tree"],
	default="blob",
	help="Specify type of file to be hashed"
)

argsp.add_argument(
	"-w",
	dest="write",
	action="store_true",
	help="Write to hash of object into storage"
)

argsp.add_argument(
	"path",
	help="Read object from <file>"
)

def cmd_hash_object(args):
	if args.write:
		repo = GitRepository(".")
	else:
		repo=None

	with open(args.path, "rb") as fd:
		sha = object_hash(fd, args.type.encode(), repo)
		print(sha)

def object_hash(fd, fmt, repo=None):
	data = fd.read()

	if   fmt == b'commit': obj = GitCommit(repo, data)
	elif fmt == b'tree'  : obj = GitTree(repo, data)
	elif fmt == b'tag'   : obj = GitTag(repo, data)
	elif fmt == b'blob'  : obj = GitBlob(repo, data)
	else: 
		raise Exception("Unknown type %s" % fmt)

	return object_write(obj, repo)

# Key-value list with message parser
def kvlm_parse(raw, start=0, dct=None):
	if not dct:
		dct = collections.OrderedDict()

	spc = raw.find(b' ', start)
	nl = raw.find(b'\n', start)

	if (spc < 0) or (nl < spc):
		assert(nl == start)
		dct[b''] = raw[start + 1:]
		return dct

	key = raw[start: spc]

	end = start
	while True:
		end = raw.find(b'\n', end + 1)
		if raw[end + 1] != ord(' '): break

	value = raw[spc + 1: end].replace(b'\n', b'\n')

	if key in dct:
		if type(dct[key]) == list:
			dct[key].append(value)
		else:
			dct[key] = [ dct[key], value ]

	else:
		dct[key] = value

	return kvlm_parse(raw, start=end + 1, dct=dct)

def kvlm_serialize(kvlm):
	ret = b''

	for k in kvlm.keys():
		if k == b'': continue

		val = kvlm[k]

		if type(val) != list:
			val = [ val ]

		for v in val:
			ret += k + b' ' + (v.replace(b'\n', b'\n ')) + b'\n'

	ret += b'\n' + kvlm[b'']

	return ret

class GitCommit(GitObject):
	fmt = b'commit'

	def deserialize(self, data):
		self.kvlm = kvlm_parse(data)

	def serialize(self):
		return kvlm_serialize(self.kvlm)

argsp = argsubparsers.add_parser("log", help="Display history of given commit.")
argsp.add_argument(
	"commit",
	default="HEAD",
	nargs="?",
	help="Commit to start at."
)

def cmd_log(args):
	repo = repo_find()

	print("digraph umplog{")
	log_graphviz(repo, object_find(repo, args.commit), set())
	print("}")

def log_graphviz(repo, sha, seen):
	if sha in seen: return

	seen.add(sha)

	commit = object_read(repo, sha)
	assert(commit.fmt == b'commit')

	if not b'parent' in commit.kvlm.keys():
		return

	parents = commit.kvlm[b'parent']

	if type(parents) != list:
		parents = [ parents ]

	for p in parents:
		p.decode("ascii")
		print("c_{0} -> c_{1}".format(sha, p))
		log_graphviz(repo, p, seen)

class GitTreeLeaf(object):
	def __init__(self, mode, path, sha):
		self.mode = mode
		self.path = path
		self.sha = sha

def tree_parse_one(raw, start=0):
	x = raw.find(b' ', start)
	assert(x - start == 5 or x - start == 6)

	mode = raw[start:x]

	y = raw.find(b'\x00', x)
	path = raw[x + 1:y]

	sha = hex( int.from_bytes(raw[y + 1: y + 21], "big") )

	return y + 21, GitTreeLeaf(mode, path, sha)

def tree_parse(raw):
	pos = 0
	max = len(raw)
	ret = list()

	while pos < max:
		pow, data = tree_parse_one(raw, pos)
		ret.append(data)

	return ret

def tree_serialize(obj):
	ret = b''
	for i in obj.items:
		ret += i.mode + b' ' + i.path + b'\x00'
		sha = int(i.sha, 16)
		ret += sha.to_bytes(20, byteorder="big")

	return ret

class GitTree(GitObject):
	fmt = b'tree'

	def deserialize(self, data):
		self.item = tree_parse(data)

	def serialize(self):
		return tree_serialize(self)

# CLI argument parser for ls-tree command
argsp = argsubparsers.add_parser("ls-tree", help="Pretty-print a tree object")
argsp.add_argument("object", help="The object to show.")

def cmd_ls_tree(args):
	repo = repo_find()
	obj = object_read(repo, object_find(repo, args.object, fmt=b'tree'))

	for item in obj.items:
		print("{0} {1} {2}\t{3}".format(
			"0" * (6 - len(item.mode)) + item.mode.decode("ascii"),
			object_read(repo, item.sha).fmt.decode("ascii"),
			item.sha,
			item.path.decode("ascii")
		))

# Argument parser for CLI command checkout
argsp = argsubparsers.add_parser("checkout", help="Checkout a commit inside of a directory.")
argsp.add_argument("commit", help="The commit or tree to checkout.")
argsp.add_argument("path", help="The EMPTY directory to checkout on.")

def cmd_checkout(args):
	repo = repo_find()

	obj = object_read(repo, object_find, (repo, args.commit))

	if obj.fmt == b'commit':
		obj = object_read(repo, obj.kvlm[b'tree'].decode("ascii"))

	if os.path.exists(args.path):
		if not os.path.isdir(args.path):
			raise Exception("Not a directory {0}".format(args.path))
		if os.listdir(args.path):
			raise Exception("Not empty {0}".format(args.path))
	
	else:
		os.makedirs(args.path)

	tree_checkout(repo, obj, os.path.realpath(args.path).encode())

def tree_checkout(repo, tree, path):
	for item in tree.items:
		obj = object_read(repo, item.sha)
		dest = os.path.join(path, item.path)

		if obj.fmt == b'tree':
			os.mkdir(dest)
			tree_checkout(repo, obj, dest)
		elif obj.fmt == b'blob':
			with open(dest, "wb") as f:
				f.write(obj.blobdata)

def ref_resolve(repo, ref):
	with open(repo_file(repo, ref), "r") as fp:
		data = fp.read()[:-1]

	if data.startswith("ref: "):
		return ref_resolve(repo, data[5:])
	else:
		return data

def ref_list(repo, path=None):
	if not path:
		path = repo_dir(repo, "refs")
	
	ret = collections.OrderedDict()

	for f in sorted(os.listdir(path)):
		can = os.path.join(path, f)
		if os.path.isdir(can):
			ret[f] = ref_list(repo, can)
		else:
			ret[f] = ref_resolve(repo, can)
	
	return ret

argsp = argsubparsers.add_parser("show-ref", help="List references")

def cmd_show_ref(args):
	repo = repo_find()
	refs = ref_list(repo)
	show_ref(repo, refs, prefix="refs")

def show_ref(repo, refs, with_hash=True, prefix=""):
	for k, v in refs.items():
		if type(v) == str:
			print("{0}{1}{2}".format(
				v + " " if with_hash else "",
				prefix + "/" if prefix else "",
				k
			))

		else:
			show_ref(repo, v, with_hash=with_hash, prefix="{0}{1}{2}".format(prefix, "/" if prefix else "", k))

class GitTag(GitCommit):
	fmt = b'tag'

argsp = argsubparsers.add_parser(
		"tag",
		help="List and create tags"
)

argsp.add_argument(
	"-a",
	action="store_true",
	dest="create_tag_object",
	help="Whether to create a tag object"
)

argsp.add_argument(
	"name",
	nargs="?",
	help="The new tag's name"
)

argsp.add_argument(
	"object",
	default="HEAD",
	nargs="?",
	help="The object the new tag will point to"
)

def cmd_tags(args):
	repo = repo_find()

	if args.name:
		tag_create(
			args.name,
			args.object,
			type="object" if args.create_tag_object else "ref"
		)

	else:
		refs = ref_list(repo)
		show_ref(repo, refs["tags"], with_hash=False)

def object_resolve(repo, name):
	"""Resolve name to object hash in repo

This function is aware of:

	- the HEAD literal
	- short and long hashes
	- tags
	- branches
	- remote branches"""

	candidates = list()
	hashRE = re.compile(r"^[0-9A-Fa-f]{1,16}$")
	smallHashRE = re.compile(r"^[0-9A-Fa-f]{1,16}$")

	if not name.strip():
		return None

	if name == "HEAD":
		return [ ref_resolve(repo, "HEAD") ]

	if hashRE.match(name):
		if len(name) == 40:
			return [ name.lower() ]
		elif len(name) >= 4:
			name = name.lower()
			prefix = name[0:2]
			path = repo_dir(repo, "objects", prefix, mkdir=False)
			if path:
				rem = name[2:]
				for f in os.listdir(path):
					if f.startswith(rem):
						candidates.append(prefix + f)

	return candidates

argsp = argsubparsers.add_parser("rev-parse",	help="Parse revision (or other objects )identifiers")

argsp.add_argument(
	"--ump-type",
	metavar="type",
	dest="type",
	choices=["blob", "commit", "tag", "tree"],
	default=None,
	help="Specify the expected type"
)

argsp.add_argument("name", help="The name to parse")

def cmd_rev_parse(args):
	if args.type:
		fmt = args.type.encode()

	repo = repo_find()

	print (object_find(repo, args.name, args.type, follow=True))

class GitIndexEntry(object):
	ctime = None
	"""The last time a file's metadata changed.  This is a tuple (seconds, nanoseconds)"""

	mtime = None
	"""The last time a file's data changed.  This is a tuple (seconds, nanoseconds)"""

	dev = None
	"""The ID of device containing this file"""
	ino = None
	"""The file's inode number"""
	mode_type = None
	"""The object type, either b1000 (regular), b1010 (symlink), b1110 (gitlink). """
	mode_perms = None
	"""The object permissions, an integer."""
	uid = None
	"""User ID of owner"""
	gid = None
	"""Group ID of ownner (according to stat 2.  Isn'th)"""
	size = None
	"""Size of this object, in bytes"""
	obj = None
	"""The object's hash as a hex string"""
	flag_assume_valid = None
	flag_extended = None
	flag_stage = None
	flag_name_length = None
	"""Length of the name if < 0xFFF (yes, three Fs), -1 otherwise"""

	name = None