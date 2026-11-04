Installation
============

This documentation describes the 2.x functional preview. Install the exact version::

    uv tool install --prerelease allow 'modpoll[serial]==2.0.0a2'

For existing CSV installations use ``uv tool install 'modpoll<2'`` and the
`1.x documentation <https://top-maker.github.io/modpoll/1.x/>`_.
The preview image is ``topmaker/modpoll:2.0.0a2``; stable ``latest`` stays on 1.x.
See :doc:`v1-compatibility` for tested platforms and hardware limitations.

This program is tested on python 3.10+ (Ubuntu 22.04+ or equivalent). Ubuntu 20.04 and python 3.8 are no longer supported.

Install with uv
---------------

The package is available in the `Python Package Index <https://pypi.org/>`_,

.. code-block:: shell

    uv tool install --prerelease allow "modpoll==2.0.0a2"

Optionally, pyserial library can be installed for Modbus-RTU communication,

.. code-block:: shell

    uv tool install --prerelease allow 'modpoll[serial]==2.0.0a2'

Run the following command to check if there is new version available,

.. code-block:: shell

    uv tool install --upgrade --prerelease allow "modpoll<3"

Uninstall
---------

The program can be uninstalled by the following command,

.. code-block:: shell

    uv tool uninstall modpoll


Run with docker
---------------

A docker image has been provided for user to directly use the tool
without the local installation,

.. code-block:: shell

    docker run --rm topmaker/modpoll:2.0.0a2

It shows the version of the tool by default.
