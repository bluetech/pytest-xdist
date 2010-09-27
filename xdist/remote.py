"""
    This module is executed in remote subprocesses and helps to
    control a remote testing session and relay back information.
    It assumes that 'py' is importable and does not have dependencies
    on the rest of the xdist code.  This means that the xdist-plugin
    needs not to be installed in remote environments.
"""

import sys, os

class SlaveInteractor:
    def __init__(self, config, channel):
        self.config = config
        self.slaveid = config.slaveinput.get('slaveid', "?")
        self.log = py.log.Producer("slave-%s" % self.slaveid)
        if not config.option.debug:
            py.log.setconsumer(self.log._keywords, None)
        self.channel = channel
        config.pluginmanager.register(self)

    def sendevent(self, name, **kwargs):
        self.log("sending", name, kwargs)
        self.channel.send((name, kwargs))

    def pytest_internalerror(self, excrepr):
        for line in str(excrepr).split("\n"):
            self.log("IERROR> " + line)

    def pytest_sessionstart(self, session):
        self.session = session
        self.collection = session.collection
        slaveinfo = getinfodict()
        self.sendevent("slaveready", slaveinfo=slaveinfo)

    def pytest_sessionfinish(self, __multicall__, exitstatus):
        self.config.slaveoutput['exitstatus'] = exitstatus
        res = __multicall__.execute()
        self.sendevent("slavefinished", slaveoutput=self.config.slaveoutput)
        return res

    def pytest_perform_collection(self, session):
        self.sendevent("collectionstart")

    def pytest_runtest_mainloop(self, session):
        self.log("entering main loop")
        while 1:
            name, kwargs = self.channel.receive()
            self.log("received command %s(**%s)" % (name, kwargs))
            if name == "runtests":
                ids = kwargs['ids']
                for nodeid in ids:
                    for item in self.collection.getbyid(nodeid):
                        self.config.hook.pytest_runtest_protocol(item=item)
            elif name == "shutdown":
                break
        return True

    def pytest_log_finishcollection(self, collection):
        ids = [collection.getid(item) for item in collection.items]
        self.sendevent("collectionfinish",
            topdir=str(collection.topdir),
            ids=ids)

    #def pytest_runtest_logstart(self, nodeid, location):
    #    self.sendevent("logstart", nodeid=nodeid, location=location)

    def pytest_runtest_logreport(self, report):
        data = serialize_report(report)
        self.sendevent("testreport", data=data)

    def pytest_collectreport(self, report):
        data = serialize_report(report)
        self.sendevent("collectreport", data=data)

def serialize_report(rep):
    import py
    d = rep.__dict__.copy()
    d['longrepr'] = rep.longrepr and str(rep.longrepr) or None
    for name in d:
        if isinstance(d[name], py.path.local):
            d[name] = str(d[name])
        elif name == "result":
            d[name] = None # for now
    return d

def getinfodict():
    import platform
    return dict(
        version = sys.version,
        version_info = tuple(sys.version_info),
        sysplatform = sys.platform,
        platform = platform.platform(),
        executable = sys.executable,
        cwd = os.getcwd(),
    )

def remote_initconfig(config, option_dict, args):
    config._preparse(args)
    config.option.__dict__.update(option_dict)
    config.option.looponfail = False
    config.option.usepdb = False
    config.option.dist = "no"
    config.option.distload = False
    config.option.numprocesses = None
    config.args = args
    return config
    

if __name__ == '__channelexec__':
    slaveinput,args,option_dict = channel.receive()
    import py
    config = remote_initconfig(py.test.config, option_dict, args)
    config.slaveinput = slaveinput
    config.slaveoutput = {}
    interactor = SlaveInteractor(config, channel)
    config.hook.pytest_cmdline_main(config=config)