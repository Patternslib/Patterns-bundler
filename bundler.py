from distutils.dir_util import copy_tree
from lxml import etree
from pyramid.config import Configurator
from pyramid.response import Response
from wsgiref.simple_server import make_server
from zipfile import ZipFile

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess


html_parser = etree.HTMLParser()
log = logging.getLogger('bundler')

parser = argparse.ArgumentParser()
parser.add_argument(
    '--host',
    dest='host',
    default='localhost',
    help='Host to listen on. Defaults lo localhost.',
)
parser.add_argument(
    '--port',
    dest='port',
    type=int,
    default=2652,
    help='port to listen on. Defaults to 8080.',
)
parser.add_argument(
    '--websitedir',
    dest='websitedir',
    default='../Patterns-site',
    help='Path to the Patterns checkout.',
)
parser.add_argument(
    '--patternsdir',
    dest='patternsdir',
    default='../project-scaffold',
    help='Path to the project scaffold.',
)
cargs = parser.parse_args()
patternsdir = os.path.abspath(cargs.patternsdir)
websitedir = os.path.abspath(cargs.websitedir)

version = json.load(
    open(patternsdir+"/package.json", "rb"))['version'].encode('utf-8')

TPL_head = """/* Patterns bundle configuration.
*
* This file is used to tell webpack.config.js which Patterns to load when it
* generates a bundle.
*/

define([
    "jquery",
    "pat-registry",
"""

TPL_tail = """
], function($, registry) {
    // Since we are in a non-AMD env, register a few useful utilites
    var window = require("window");
    window.jQuery = $;
    require("imports-loader?this=>window!jquery.browser");

    $(function () {
        registry.init();
    });
    return registry;
});
"""


def build_js(modules, bundlehash, bundlename, bundledir_path, uglify):
    tmp_bundledir = os.path.join(bundledir_path, "tmp")
    copy_tree(patternsdir,
              tmp_bundledir)

    # parse query string for patterns and add them
    module_str = ",\n".join(["'%s'" % m for m in modules])
    custom_config = "%s\n%s\n%s" % (TPL_head, module_str, TPL_tail)
    log.info(custom_config)
    data = open(os.path.join(tmp_bundledir, 'bundle-config.js'), 'wb')
    data.write(custom_config)
    data.close()
    open(os.path.join(tmp_bundledir, 'VERSION.txt'), 'w').write(
        '/*! Version %s\nCustom Config:\n%s\n */' % (version, module_str))

    initial_dir = os.getcwd()
    os.chdir(tmp_bundledir)
    cmdline = "cd {0} && NODE_ENV=production node_modules/.bin/webpack --config webpack.config.js".format(
        tmp_bundledir
    )
    subprocess.call(cmdline.split(" "), shell=True)
    os.chdir(initial_dir)
    copy_tree(os.path.join(tmp_bundledir, "bundles"),
              os.path.join(bundledir_path, "js"))


def build_css(bundledir_path, modules, minify, bundlename):
    scss_path = os.path.abspath(os.path.join(
        bundledir_path, "tmp", "patterns.scss"))
    initial_dir = os.getcwd()
    os.chdir(patternsdir)
    with open(scss_path, "w") as patterns_scss:
        patterns_scss.write(
            '@import "{0}/_sass/_settings.scss";\n'.format(patternsdir))
        patterns_scss.write(
            '@import "{0}/_sass/_mixins.scss";\n'.format(patternsdir))
        patterns_scss.write(
            '@import "{0}/_sass/components/_button.scss";\n'.format(patternsdir))
        patterns_scss.write(
            '@import "{0}/_sass/components/_button-bar.scss";\n'.format(patternsdir))
        patterns_scss.write(
            '@import "{0}/_sass/components/_avatar.scss";\n'.format(patternsdir))
        patterns_scss.write(
            '@import "{0}/_sass/components/_form.scss";\n'.format(patternsdir))
        patterns_scss.write(
            '@import "{0}/_sass/components/_icon.scss";\n'.format(patternsdir))
        for module in modules:
            module_name = module.replace("pat-", "")
            module_scss_path = "{0}/src/pat/{1}/_{1}.scss".format(
                patternsdir, module_name)
            if os.path.exists(module_scss_path):
                patterns_scss.write(
                    '@import "{0}";\n'.format(module_scss_path))

    sass_cmd = subprocess.Popen(
        ["sass",
            "--style={0}".format("compressed" if minify else "nested"), scss_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    with open(
            os.path.join(bundledir_path, "style", bundlename+".css"), "w") as css_file:
        css, error = sass_cmd.communicate()
        css_file.write(css)
    os.chdir(initial_dir)


def build_html(modules, bundledir_path, bundlename):
    copy_tree(os.path.join(patternsdir, "style"),
              os.path.join(bundledir_path, "style"))
    copy_tree(os.path.join(websitedir, 'style'),
              os.path.join(bundledir_path, "style", "website"))

    for module in modules:
        module_name = module.replace("pat-", "")
        module_path = "{0}/src/pat/{1}/".format(patternsdir, module_name)
        if not os.path.exists(module_path):
            continue
        module_files = os.listdir(module_path)
        docs_path = os.path.join(bundledir_path, "docs", module_name)
        if not os.path.exists(docs_path):
            os.makedirs(docs_path)
        for module_resource in module_files:
            extension = os.path.splitext(module_resource)[1]
            if extension not in [".scss", ".js", ".css", ".psd"]:
                path = os.path.join(module_path, module_resource)
                if os.path.isfile(path):
                    shutil.copy(path, docs_path)
                    if extension == ".html":
                        with open(os.path.join(docs_path, module_resource), "r+") as html_file:
                            tree = etree.parse(html_file, html_parser)
                            for node in tree.xpath("//head/link|//script"):
                                node.getparent().remove(node)
                            print "fixing up: {0}".format(docs_path)
                            head = tree.xpath("//head")
                            if head:
                                head_elem = head[0]
                                head_elem.append(etree.XML("""
<script src="../../js/{0}.js" type="text/javascript" charset="utf-8"> </script>
                                """.format(bundlename)))
                                head_elem.append(etree.XML("""
<link rel="stylesheet" href="../../style/website/fontello/css/fontello.css" type="text/css"/>
                                """.format(bundlename)))
                                head_elem.append(etree.XML("""
<link rel="stylesheet" href="../../style/fontello/css/fontello.css" type="text/css"/>
                                """.format(bundlename)))
                                head_elem.append(etree.XML("""
<link rel="stylesheet" href="../../style/patterns.css" type="text/css"/>
                                """))
                                head_elem.append(etree.XML("""
<link rel="stylesheet" href="../../style/{0}.css" type="text/css"/>
                                """.format(bundlename)))
                            html_file.seek(0)
                            html_file.truncate()
                            html_file.write(etree.tostring(tree))

                elif os.path.isdir(path):
                    shutil.copytree(path, os.path.join(
                        docs_path, module_resource))


def build_zipfile(bundlezip_path, bundledir_path):
    with ZipFile(bundlezip_path, "w") as bundlezip:
        initial_dir = os.getcwd()
        os.chdir(bundledir_path)
        for base, dirs, files in os.walk("."):
            for file_name in files:
                file_path = os.path.join(base, file_name)
                if "/tmp/" not in file_path and "/cache/" not in file_path:
                    bundlezip.write(file_path)
                    print "adding %s" % file_path
        os.chdir(initial_dir)


def make_bundle(request):
    if len(request.GET.keys()) == 0:
        data = open('index.html', 'rb').read()
        mResponse = Response(data)
        mResponse.headers['content-type'] = 'text/html'
        return mResponse

    modules = [
        x.replace('pat/', 'pat-')
        for x in request.GET.keys()
        if x.startswith('pat/') or x in ('modernizr', 'less', 'prefixfree')
    ]
    modules.sort()

    log.info("Modules: %s" % str(modules))

    minify = request.GET.get('minify') == 'on' and '.min' or ''
    uglify = minify and 'uglify' or 'none'

    hashkey = hashlib.new('sha1')
    hashkey.update('-'.join(modules))
    # maybe indicate if it's full, core or custom in the name?
    bundlename = "patterns-{0}{1}".format(version, "-min" if minify else "")
    bundlehash = "{0}-{1}".format(bundlename, hashkey.hexdigest())
    bundledir_path = os.path.abspath(os.path.join("bundlecache", bundlehash))
    bundlezip_path = "bundlecache/{0}.zip".format(bundlehash)

    log.info('Hashkey generated: {0}'.format(hashkey.hexdigest()))
    log.info('Bundlehash generated: {0}'.format(bundlehash))

    # Create cache dir if it doesn't exist yet
    if not os.path.exists("bundlecache"):
        os.makedirs('bundlecache')

    if not os.path.exists(bundlezip_path):
        if not os.path.exists(bundledir_path):
            shutil.copytree("skel", bundledir_path)
        build_js(modules, bundlehash, bundlename, bundledir_path, uglify)
#        build_css(bundledir_path, modules, minify, bundlename)
#        build_html(modules, bundledir_path, bundlename)
        build_zipfile(bundlezip_path, bundledir_path)

    data = open(bundlezip_path, 'rb').read()
    mResponse = Response(data)
    mResponse.headers['content-type'] = 'application/zip'
    mResponse.headers[
        'content-disposition'] = 'attachment;filename={0}.zip'.format(bundlename)

    return mResponse

if __name__ == '__main__':
    config = Configurator()
    config.add_route('getBundle', '/getBundle')
    config.add_view(make_bundle, route_name='getBundle')
    app = config.make_wsgi_app()
    server = make_server(cargs.host, cargs.port, app)
    server.serve_forever()
