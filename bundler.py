import argparse
import json
import os
import hashlib
import logging
import shutil
import subprocess
import tempfile
from pyramid.config import Configurator
from pyramid.response import Response
from wsgiref.simple_server import make_server

log = logging.getLogger('bundler')

parser = argparse.ArgumentParser()
parser.add_argument('--host', dest='host', default='localhost', help='Host to listen on. Defaults lo localhost.')
parser.add_argument('--port', dest='port', type=int, default=8080, help='port to listen on. Defaults to 8080.')
parser.add_argument('--patternsdir', dest='patternsdir', default='../Patterns', help='Path to the Patterns checkout.')
cargs = parser.parse_args()
patternsdir = os.path.abspath(cargs.patternsdir)

version = json.load(open(patternsdir+"/package.json", "rb"))['version'].encode('utf-8')

TPL_head = """/* Patterns bundle configuration.
*
* This file is used to tell r.js which Patterns to load when it generates a
* bundle. This is only used when generating a full Patterns bundle, or when
* you want a simple way to include all patterns in your own project. If you
* only want to use selected patterns you will need to pull in the patterns
* directly in your RequireJS configuration.
*/

define([
    "jquery",
    "pat-registry",
    "logging",
    "pat-parser",
    "pat-htmlparser",
    "pat-depends_parse",
    "pat-dependshandler",
"""

TPL_tail = """
], function($, registry) {
    window.patterns = registry;
    $(function () {
        registry.init();
    });
    return registry;
});
"""


def make_bundle(request):
    if len(request.GET.keys())==0:
        data = open('index.html','rb').read()
        mResponse = Response(data)
        mResponse.headers['content-type'] = 'text/html'
        return mResponse
           
    # string that contains all the patterns that are to be included
    custom_config = "" 
    modules = [x.replace('pat/', 'pat-') for x in request.GET.keys() if x.startswith('pat/') or x in ('modernizr', 'less', 'prefixfree')]
    modules.sort()

    log.info( "Modules: %s" % str(modules) )

    minify = not not request.GET.get('minify',False) and '.min' or ''
    uglify = not not request.GET.get('minify',False) and 'uglify' or 'none'

    hashkey = hashlib.new('sha1')
    hashkey.update('-'.join(modules))
    bundlename = "patterns-%s-%s%s.js" %  ( version, hashkey.hexdigest(), minify )
    
    log.info('Hashkey generated: %s' % hashkey.hexdigest() )
    log.info('Bundlename generated: %s' % bundlename)

    # Create cache dir if it doesn't exist yet
    if not os.access("bundlecache", os.F_OK):
        os.makedirs('bundlecache')

    if not os.access("bundlecache/%s" % bundlename, os.F_OK):
        # build

        if not os.access(patternsdir+"/build-custom.js", os.F_OK):
            buildfile = open(patternsdir+'/build.js', 'rb').read().replace('"patterns": "patterns"', '"patterns": "patterns-custom"')
            open(patternsdir+'/build-custom.js', 'wb').write(buildfile)

        # XXX if bundlename in cache, return that

        # parse query string for patterns and add them
        module_str = ",\n".join(["'%s'" % m for m in modules])
        custom_config = "%s\n%s\n%s" % (TPL_head, module_str, TPL_tail)
        log.info(custom_config)
        data = open(patternsdir+'/src/patterns-custom.js', 'wb')
        data.write(custom_config)
        data.close()
    
        #os.chdir(cargs.patternsdir)  
        # call the r.js with alternate params for  out, include, optimize and insertREquire statements
        # place output file into a cache directory
        subprocess.call([patternsdir+"/node_modules/.bin/r.js", 
                         "-o", 
                         patternsdir+"/build-custom.js" , 
                         "out=bundlecache/"+bundlename, 
                         "include=patterns-custom", 
                         "insertRequire=patterns-custom", 
                         "optimize="+uglify])
        
        
    data = open("bundlecache/%s" % bundlename, 'rb').read() # create response with bundle.js as attachment
    mResponse = Response(data)
    mResponse.headers['content-type'] = 'application/javascript'
    mResponse.headers['content-disposition'] = 'attachment;filename=%s' % bundlename    

    return mResponse

if __name__ == '__main__':              
    config = Configurator()
    config.add_route('getBundle', '/getBundle')
    config.add_view(make_bundle, route_name='getBundle')
    app = config.make_wsgi_app()
    server = make_server(cargs.host, cargs.port, app)
    server.serve_forever()
