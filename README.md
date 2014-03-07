# Patterns-bundler

The server that generates custom patterns bundles from the website.

The bundler is a pyramid server that takes a request listing a number of 
patterns and builds a custom patterns bundle using a Patterns checkout.

The long term vision is that this will also allow to include custom packages 
fetched from bower and a registry that provides these custom packages for 
selection.

# Installation

## Bundler

pip install pyramid and then start the server by running python bundler.py. 
You must provide host, port and the path to the Patterns checkout that should 
be used.

## Circus

To run the server in the background you can use circus. You need to pip install 
circus and circus-web to run it
