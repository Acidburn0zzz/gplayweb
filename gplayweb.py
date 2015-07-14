#! /usr/bin/python2
# -*- coding: utf-8 -*-
import sys, os, traceback, ConfigParser, argparse, multiprocessing
import tornado.ioloop, tornado.web
from gplaycli.gplaycli import GPlaycli


# Main handler
class MainHandler(tornado.web.RequestHandler):
	def __init__(self, *args, **kwargs):
		tornado.web.RequestHandler.__init__(self,*args, **kwargs)
		self.cli = cli
		# Get conf
		# Where apk are stored
		self.apk_folder = config['folder']
		if not os.path.isdir(self.apk_folder):
			os.mkdir(self.apk_folder)
		# Root of the HTTP URL
		self.root_url = config['root_url']
		self.cache_file = '.cache'

		self.fdroid = False
		# FDroid support is asked
		if 'fdroid_repo_dir' in config:
			self.fdroid=True
			self.fdroid_repo_dir = config['fdroid_repo_dir']
			self.fdroid_script_dir = config['fdroid_script_dir']
			sys.path.append(self.fdroid_script_dir)
			self.fdroid_update = __import__('fdroidserver.update', fromlist=['create_metadata_and_update'])
			# If custom category is specified
			if 'fdroid_custom_category' in config:
				self.fdroid_custom_category = config['fdroid_custom_category']

	# Routes
	def get(self):
		page = self.get_argument('page',None)
		if page == None:
			self.redirect('list')
		elif page == 'list':
			self.list()
		elif page == 'search':
			self.search()
		elif page == 'download':
			self.download()
		elif page == 'remove':
			self.remove()
		elif page == 'downloadfromserver':
			self.download_from_server()
		elif page == 'emptycache':
			self.empty_cache()
		else:
			return

	def redirect(self,url,permanent=False,status=None):
		super(MainHandler,self).redirect(self.root_url+"?page="+url, permanent, status)

	# Templates
	def get_template_path(self):
		return os.path.dirname(os.path.abspath(__file__))+"/templates"

	def render(self, mode, items, **kwargs):
		super(MainHandler,self).render(mode+".html", title="GPlayWeb", ROOT=self.root_url, items=items, **kwargs)
	

	# Core
	# Show the list of downloaded apks
	def list(self):
		results = self.cli.list_folder_apks(self.apk_folder)
		cached_infos = self.get_infos(results)
		self.render('list', cached_infos)

	# ask gplay api if infos are not cached
	def get_infos(self, apks):
		apks = map(self.kick_extension, apks)
		separator = ";"
		# Ensure the cache file exists
		open(self.cache_file,'a+')
		cached_infos = dict()
		for line in open(self.cache_file).read().splitlines():
			infos = line.split(separator)
			apk_name = infos[0]
			if apk_name not in apks:
				continue
			infos.pop(0)
			cached_infos[apk_name] = infos 
		apks = set(apks)-set(cached_infos.keys())
		details = self.cli.get_bulk_details(apks)

		buff = open(self.cache_file,'a')
		for apk in details:
			if details[apk][0]=='':
				details[apk][0]=apk
			buff.write(apk+separator+separator.join(details[apk]).encode('utf-8')+'\n')
		buff.close()
		cached_infos.update(details)
		return cached_infos

	def empty_cache(self):
		os.remove(self.cache_file)
		self.redirect('list')

	# Search an apk by string
	def search(self):
		search_string = self.get_argument('name', None)
		if search_string == None:
			self.render('form_search', None)
			return
		number = self.get_argument('number',10)
		results = self.cli.search(list(),search_string,number, free_only=False)
		if results == None:
			results = [["No Result"]]
		self.render('search', results, string=search_string, number=number)

	# Download an apk by codename to the server (org.mozilla.firefox)
	def download(self):
		package = self.get_argument('name', None)
		if package == None:
			self.render('download_ask', None)
			return
		self.cli.set_download_folder(self.apk_folder)
		self.cli.download_packages([package])
		# Update fdroid repo if asked
		self.multiproc_update_fdroid()
		self.redirect('list')

	# Remove the apk from the folder
	def remove(self):
		filename = self.get_argument('name', None)
		filename = os.path.basename(filename)+'.apk'
		os.remove(os.path.join(self.apk_folder, filename))
		# Update fdroid repo if asked
		self.multiproc_update_fdroid()
		self.redirect('list')
	
	# Download the available apk from the server
	def download_from_server(self):
		filename = self.get_argument('name', None)
		base_filename = os.path.basename(filename)+'.apk'
		filename = os.path.join(self.apk_folder, base_filename)
		buf_size = 4096
		self.set_header('Content-Type', 'application/octet-stream')
		self.set_header('Content-Disposition', 'attachment; filename=' + base_filename)
		with open(filename, 'r') as f:
			while True:
				data = f.read(buf_size)
				if not data:
					break
				self.write(data)
		self.finish()


	def multiproc_update_fdroid(self):
		queue = multiprocessing.Queue()
		p = multiprocessing.Process(target=self.updateFdroidRepo)
		p.start()

	def updateFdroidRepo(self):
		# If Fdroid not asked
		if not self.fdroid:
			return

		# We change dir path cause Fdroid does not support
		# remote update, it needs to be in the same folder
		current_dir = os.path.dirname(os.path.realpath(__file__))
		os.chdir(self.fdroid_repo_dir)
		# We update fdroidserver repo
		try:
			self.fdroid_update.create_metadata_and_update()
			self.customize_metadata()
			self.fdroid_update.create_metadata_and_update()
		except:
			traceback.print_exc(file=sys.stdout)
		# We return to our original path
		os.chdir(current_dir)

	# Add custom category to downloaded apps
	def customize_metadata(self):
		for metadir, dirnames, metafiles in os.walk('metadata'):
			for metafile in metafiles:
				if metafile.endswith('.txt'):
					metafile = os.path.join('metadata',metafile)
					buff = open(metafile, 'a+')
					if 'Categories:' not in buff.read():
						buff.write('Categories:'+self.fdroid_custom_category+'\n')
					buff.close()

	# Delete the extension of the given string
	def kick_extension(self,apkfile):
		return os.path.splitext(apkfile)[0]



def default_params():
	config = {
		'ip': '0.0.0.0',
		'port': '8888',
		'root_url': '/',
		'folder': 'repo',
		'fdroid_custom_category': 'GPlayWeb',
	}
	return config

def check_config(config):
	if ('fdroid_repo_dir' in config and 'fdroid_script_dir' not in config)\
		or ('fdroid_script_dir' in config and 'fdroid_repo_dir' not in config):
		return False, "Need to define both 'fdroid_repo_dir' and 'fdroid_script_dir' to support Fdroid server update! "
	return True, "Success"

def main():
	global cli_args, config, cli
	# Parsing CLI arguments
	parser = argparse.ArgumentParser(description="A web interface for GPlayCli")
	parser.add_argument('-c','--config',action='store',dest='CONFFILE',metavar="CONF_FILE",nargs=1,
			type=str,default=os.path.dirname(os.path.abspath(__file__))+"/gplayweb.conf",
			help="Use a different config file than gplayweb.conf")
	cli_args = parser.parse_args()
	configparser = ConfigParser.ConfigParser()
	configparser.read(cli_args.CONFFILE)
	config_list = configparser.items("Server")

	# Get default params
	config = default_params()
	# Override default params
	for key, value in config_list:
		config[key] = value

	status, errorString = check_config(config)
	# If something went wrong
	if not status:
		print errorString
		return

	settings = {
		"static_path": os.path.join(os.path.dirname(__file__), "static"),
		"root_url": r""+config['root_url'],
		"port": r""+config['port'],
		"ip": r""+config['ip']
	}
	application = tornado.web.Application([
		(settings['root_url'], MainHandler),
		(r"/static/", tornado.web.StaticFileHandler,
		 dict(path=settings['static_path'])),
	], **settings)

	# Parsing conffile
	cli = GPlaycli(cli_args.CONFFILE)
	# Connect to API
	cli.connect_to_googleplay_api()

	application.listen(settings['port'],settings['ip'])
	tornado.ioloop.IOLoop.current().start()

if __name__ == "__main__":
	main()