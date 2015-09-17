"""
XML Test Runner for PyUnit
"""

# Written by Sebastian Rittau <srittau@jroger.in-berlin.de> and placed in
# the Public Domain. With contributions by Paolo Borelli.

from __future__ import print_function

__revision__ = "$Id$"

import os.path
import re
import sys
import time
import traceback
import unittest
try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO
from xml.sax.saxutils import escape
import lxml.etree as ET


class _TestInfo(object):

    """Information about a particular test.
    
    Used by _XMLTestResult.
    
    """

    def __init__(self, test, time):
        (self._class, self._method) = test.id().rsplit(".", 1)
        self._time = time
        self._error = None
        self._failure = None

    @staticmethod
    def create_success(test, time):
        """Create a _TestInfo instance for a successful test."""
        return _TestInfo(test, time)

    @staticmethod
    def create_failure(test, time, failure):
        """Create a _TestInfo instance for a failed test."""
        info = _TestInfo(test, time)
        info._failure = failure
        return info

    @staticmethod
    def create_error(test, time, error):
        """Create a _TestInfo instance for an erroneous test."""
        info = _TestInfo(test, time)
        info._error = error
        return info

    def print_report(self, testsuite):
        """Print information about this test case in XML format to the
        supplied stream.

        """
        testcase = ET.SubElement(testsuite, "testcase")
        testcase.set('classname', self._class)
        testcase.set('name', self._method)
        testcase.set('time', '%.4f' % self._time)
        if self._failure != None:
            self._print_error(testcase, 'failure', self._failure)
        if self._error != None:
            self._print_error(testcase, 'error', self._error)

    def print_report_text(self, stream):
        #stream.write('  <testcase classname="%(class)s" name="%(method)s" time="%(time).4f">' % \
        #    {
        #        "class": self._class,
        #        "method": self._method,
        #        "time": self._time,
        #    })
        stream.write(self._method)
        if self._failure != None:
            stream.write(' ... FAILURE!\n')
            self._print_error_text(stream, 'failure', self._failure)
        if self._error != None:
            stream.write(' ... ERROR!\n')            
            self._print_error_text(stream, 'error', self._error)
        if self._failure == None and self._error == None:
            stream.write(' ... ok\n')

    def _print_error(self, testcase, tagname, error):
        """Print information from a failure or error to the supplied stream."""
        error = ET.SubElement(testcase, tagname)
        error.set('type', str(error[0].__name__))
        tb_stream = StringIO()
        traceback.print_tb(error[2], None, tb_stream)
        error.text('%s\n%s' % (str(error[1]), tb_stream.getvalue()) )

    def _print_error_text(self, stream, tagname, error):
        """Print information from a failure or error to the supplied stream."""
        text = escape(str(error[1]))
        stream.write('%s: %s\n' \
            % (tagname.upper(), text))
        tb_stream = StringIO()
        traceback.print_tb(error[2], None, tb_stream)
        stream.write(escape(tb_stream.getvalue()))
        stream.write('-'*80 + '\n')

class _XMLTestResult(unittest.TestResult):

    """A test result class that stores result as XML.

    Used by XMLTestRunner.

    """

    def __init__(self, classname):
        unittest.TestResult.__init__(self)
        self._test_name = classname
        self._start_time = None
        self._tests = []
        self._error = None
        self._failure = None

    def startTest(self, test):
        unittest.TestResult.startTest(self, test)
        self._error = None
        self._failure = None
        self._start_time = time.time()

    def stopTest(self, test):
        time_taken = time.time() - self._start_time
        unittest.TestResult.stopTest(self, test)
        if self._error:
            info = _TestInfo.create_error(test, time_taken, self._error)
        elif self._failure:
            info = _TestInfo.create_failure(test, time_taken, self._failure)
        else:
            info = _TestInfo.create_success(test, time_taken)
        self._tests.append(info)

    def addError(self, test, err):
        unittest.TestResult.addError(self, test, err)
        self._error = err

    def addFailure(self, test, err):
        unittest.TestResult.addFailure(self, test, err)
        self._failure = err

    def filter_nonprintable_text(self, text):
        return re.sub(u'[^\u0020-\uD7FF\u0009\u000A\u000D\uE000-\uFFFD\u10000-\u10FFFF]+', '', text)

    def print_report(self, report_file, time_taken, out, err):
        """Prints the XML report to the supplied stream.
        
        The time the tests took to perform as well as the captured standard
        output and standard error streams must be passed in.a

        """
        test_suite = ET.Element('testsuite')
        test_suite.set('errors', str(len(self.errors)))
        test_suite.set('failures', str(len(self.failures)))
        test_suite.set('name', self._test_name)
        test_suite.set('tests', str(self.testsRun))
        test_suite.set('time', '%.3f' % time_taken)
        for info in self._tests:
            info.print_report(test_suite)
        system_out = ET.SubElement(test_suite, 'system-out')
        system_out.text = ET.CDATA(self.filter_nonprintable_text(out))
        system_err = ET.SubElement(test_suite, 'system-err')
        system_err.text = ET.CDATA(self.filter_nonprintable_text(err))
        tree = ET.ElementTree(test_suite)
        tree.write(report_file, encoding='utf-8', pretty_print=True, xml_declaration=True)

    def print_report_text(self, stream, time_taken, out, err):
        """Prints the text report to the supplied stream.
        
        The time the tests took to perform as well as the captured standard
        output and standard error streams must be passed in.a

        """
        #stream.write('<testsuite errors="%(e)d" failures="%(f)d" ' % \
        #    { "e": len(self.errors), "f": len(self.failures) })
        #stream.write('name="%(n)s" tests="%(t)d" time="%(time).3f">\n' % \
        #    {
        #        "n": self._test_name,
        #        "t": self.testsRun,
        #        "time": time_taken,
        #    })
        for info in self._tests:
            info.print_report_text(stream)


class XMLTestRunner(object):

    """A test runner that stores results in XML format compatible with JUnit.

    XMLTestRunner(stream=None) -> XML test runner

    The XML file is written to the supplied stream. If stream is None, the
    results are stored in a file called TEST-<module>.<class>.xml in the
    current working directory (if not overridden with the path property),
    where <module> and <class> are the module and class name of the test class.

    """

    def __init__(self, result_file=None):
        self._result_file = result_file
        self._path = "."

    def run(self, test):
        """Run the given test case or test suite."""
        class_ = test.__class__
        classname = class_.__module__ + "." + class_.__name__
        if self._result_file == None:
            result_file = "TEST-%s.xml" % classname
        else:
            result_file = self._result_file

        result = _XMLTestResult(classname)
        start_time = time.time()

        # TODO: Python 2.5: Use the with statement
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = StringIO()
        sys.stderr = StringIO()

        try:
            test(result)
            try:
                out_s = sys.stdout.getvalue()
            except AttributeError:
                out_s = ""
            try:
                err_s = sys.stderr.getvalue()
            except AttributeError:
                err_s = ""
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        time_taken = time.time() - start_time
        result.print_report(result_file, time_taken, out_s, err_s)

        result.print_report_text(sys.stdout, time_taken, out_s, err_s)

        return result

    def _set_path(self, path):
        self._path = path

    path = property(lambda self: self._path, _set_path, None,
            """The path where the XML files are stored.
            
            This property is ignored when the XML file is written to a file
            stream.""")


class XMLTestRunnerTest(unittest.TestCase):
    def setUp(self):
        self._stream = StringIO()

    def _try_test_run(self, test_class, expected):

        """Run the test suite against the supplied test class and compare the
        XML result against the expected XML string. Fail if the expected
        string doesn't match the actual string. All time attribute in the
        expected string should have the value "0.000". All error and failure
        messages are reduced to "Foobar".

        """

        runner = XMLTestRunner(self._stream)
        runner.run(unittest.makeSuite(test_class))

        got = self._stream.getvalue()
        # Replace all time="X.YYY" attributes by time="0.000" to enable a
        # simple string comparison.
        got = re.sub(r'time="\d+\.\d+"', 'time="0.000"', got)
        # Likewise, replace all failure and error messages by a simple "Foobar"
        # string.
        got = re.sub(r'(?s)<failure (.*?)>.*?</failure>', r'<failure \1>Foobar</failure>', got)
        got = re.sub(r'(?s)<error (.*?)>.*?</error>', r'<error \1>Foobar</error>', got)

        self.assertEqual(expected, got)

    def test_no_tests(self):
        """Regression test: Check whether a test run without any tests
        matches a previous run.
        
        """
        class TestTest(unittest.TestCase):
            pass
        self._try_test_run(TestTest, """<testsuite errors="0" failures="0" name="unittest.TestSuite" tests="0" time="0.000">
  <system-out><![CDATA[]]></system-out>
  <system-err><![CDATA[]]></system-err>
</testsuite>
""")

    def test_success(self):
        """Regression test: Check whether a test run with a successful test
        matches a previous run.
        
        """
        class TestTest(unittest.TestCase):
            def test_foo(self):
                pass
        self._try_test_run(TestTest, """<testsuite errors="0" failures="0" name="unittest.TestSuite" tests="1" time="0.000">
  <testcase classname="__main__.TestTest" name="test_foo" time="0.000"></testcase>
  <system-out><![CDATA[]]></system-out>
  <system-err><![CDATA[]]></system-err>
</testsuite>
""")

    def test_failure(self):
        """Regression test: Check whether a test run with a failing test
        matches a previous run.
        
        """
        class TestTest(unittest.TestCase):
            def test_foo(self):
                self.assert_(False)
        self._try_test_run(TestTest, """<testsuite errors="0" failures="1" name="unittest.TestSuite" tests="1" time="0.000">
  <testcase classname="__main__.TestTest" name="test_foo" time="0.000">
    <failure type="exceptions.AssertionError">Foobar</failure>
  </testcase>
  <system-out><![CDATA[]]></system-out>
  <system-err><![CDATA[]]></system-err>
</testsuite>
""")

    def test_error(self):
        """Regression test: Check whether a test run with a erroneous test
        matches a previous run.
        
        """
        class TestTest(unittest.TestCase):
            def test_foo(self):
                raise IndexError()
        self._try_test_run(TestTest, """<testsuite errors="1" failures="0" name="unittest.TestSuite" tests="1" time="0.000">
  <testcase classname="__main__.TestTest" name="test_foo" time="0.000">
    <error type="exceptions.IndexError">Foobar</error>
  </testcase>
  <system-out><![CDATA[]]></system-out>
  <system-err><![CDATA[]]></system-err>
</testsuite>
""")

    def test_stdout_capture(self):
        """Regression test: Check whether a test run with output to stdout
        matches a previous run.
        
        """
        class TestTest(unittest.TestCase):
            def test_foo(self):
                print("Test")
        self._try_test_run(TestTest, """<testsuite errors="0" failures="0" name="unittest.TestSuite" tests="1" time="0.000">
  <testcase classname="__main__.TestTest" name="test_foo" time="0.000"></testcase>
  <system-out><![CDATA[Test
]]></system-out>
  <system-err><![CDATA[]]></system-err>
</testsuite>
""")

    def test_stderr_capture(self):
        """Regression test: Check whether a test run with output to stderr
        matches a previous run.
        
        """
        class TestTest(unittest.TestCase):
            def test_foo(self):
                print("Test", file=sys.stderr)
        self._try_test_run(TestTest, """<testsuite errors="0" failures="0" name="unittest.TestSuite" tests="1" time="0.000">
  <testcase classname="__main__.TestTest" name="test_foo" time="0.000"></testcase>
  <system-out><![CDATA[]]></system-out>
  <system-err><![CDATA[Test
]]></system-err>
</testsuite>
""")

    class NullStream(object):
        """A file-like object that discards everything written to it."""
        def write(self, buffer):
            pass

    def test_unittests_changing_stdout(self):
        """Check whether the XMLTestRunner recovers gracefully from unit tests
        that change stdout, but don't change it back properly.

        """
        class TestTest(unittest.TestCase):
            def test_foo(self):
                sys.stdout = XMLTestRunnerTest.NullStream()

        runner = XMLTestRunner(self._stream)
        runner.run(unittest.makeSuite(TestTest))

    def test_unittests_changing_stderr(self):
        """Check whether the XMLTestRunner recovers gracefully from unit tests
        that change stderr, but don't change it back properly.

        """
        class TestTest(unittest.TestCase):
            def test_foo(self):
                sys.stderr = XMLTestRunnerTest.NullStream()

        runner = XMLTestRunner(self._stream)
        runner.run(unittest.makeSuite(TestTest))


class XMLTestProgram(unittest.TestProgram):
    def runTests(self):
        if self.testRunner is None:
            self.testRunner = XMLTestRunner()
        unittest.TestProgram.runTests(self)

main = XMLTestProgram


if __name__ == "__main__":
    main(module=None)
