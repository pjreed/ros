#!/usr/bin/env python
# Software License Agreement (BSD License)
#
# Copyright (c) 2008, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Revision $Id$

"""
Library for reading and manipulating Ant JUnit XML result files.
"""

from __future__ import print_function

import os
import sys
import cStringIO
import string
import codecs
import re
import xml.etree.ElementTree as etree

import lxml.etree as ET
from xml.dom.minidom import parse, parseString
from xml.dom import Node as DomNode

import rospkg

# We need to print CDATA elements, but Python's built-in ElementTree doesn't
# support it.  So, we get to monkey patch it in.
def CDATA(text=None):
    element = etree.Element('![CDATA[')
    element.text = text
    return element

def filter_nonprintable_text(text):
    return re.sub(u'[^\u0020-\uD7FF\u0009\u000A\u000D\uE000-\uFFFD\u10000-\u10FFFF]+', '', text)

etree._original_serialize_xml = etree._serialize_xml

def _serialize_xml(write, elem, *args):
    if elem.tag == '![CDATA[':
        write("<![CDATA[%s]]>" % filter_nonprintable_text(elem.text))
        return
    return etree._original_serialize_xml(write, elem, *args)
etree._serialize_xml = etree._serialize['xml'] = _serialize_xml


class TestInfo(object):
    """
    Common container for 'error' and 'failure' results
    """
    
    def __init__(self, type_, text):
        """
        @param type_: type attribute from xml 
        @type  type_: str
        @param text: text property from xml
        @type  text: str
        """
        self.type = type_
        self.text = text

class TestError(TestInfo):
    """
    'error' result container        
    """
    def xml(self, testcase):
        error = etree.SubElement(testcase, 'error')
        error.set('type', self.type)
        error.append(CDATA(self.text))

class TestFailure(TestInfo):
    """
    'failure' result container        
    """
    def xml(self, testcase):
        error = etree.SubElement(testcase, 'failure')
        error.set('type', self.type)
        error.append(CDATA(self.text))


class TestCaseResult(object):
    """
    'testcase' result container
    """
    
    def __init__(self, name):
        """
        @param name: name of testcase
        @type  name: str
        """
        self.name = name
        self.failures = []
        self.errors = []
        self.time = 0.0
        self.classname = ''
        
    def _passed(self):
        """
        @return: True if test passed
        @rtype: bool
        """
        return not self.errors and not self.failures
    ## bool: True if test passed without errors or failures
    passed = property(_passed)
    
    def _failure_description(self):
        """
        @return: description of testcase failure
        @rtype: str
        """
        if self.failures:
            tmpl = "[%s][FAILURE]"%self.name
            tmpl = tmpl + '-'*(80-len(tmpl))
            tmpl = tmpl+"\n%s\n"+'-'*80+"\n\n"
            return '\n'.join(tmpl%x.text for x in self.failures)
        return ''

    def _error_description(self):
        """
        @return: description of testcase error
        @rtype: str
        """
        if self.errors:
            tmpl = "[%s][ERROR]"%self.name
            tmpl = tmpl + '-'*(80-len(tmpl))
            tmpl = tmpl+"\n%s\n"+'-'*80+"\n\n"
            return '\n'.join(tmpl%x.text for x in self.errors)
        return ''

    def _description(self):
        """
        @return: description of testcase result
        @rtype: str
        """
        if self.passed:
            return "[%s][passed]\n"%self.name
        else:
            return self._failure_description()+\
                   self._error_description()                   
    ## str: printable description of testcase result
    description = property(_description)
    def add_failure(self, failure):
        """
        @param failure TestFailure
        """
        self.failures.append(failure)

    def add_error(self, error):
        """
        @param failure TestError        
        """
        self.errors.append(error)

    def xml(self, testsuite):
        testcase = etree.SubElement(testsuite, 'testcase')
        testcase.set('classname', self.classname)
        testcase.set('name', self.name)
        testcase.set('time', str(self.time))
        for f in self.failures:
            f.xml(testcase)
        for e in self.errors:
            e.xml(testcase)
        
class Result(object):
    __slots__ = ['name', 'num_errors', 'num_failures', 'num_tests', \
                 'test_case_results', 'system_out', 'system_err', 'time']
    def __init__(self, name, num_errors=0, num_failures=0, num_tests=0):
        self.name = name
        self.num_errors = num_errors
        self.num_failures = num_failures
        self.num_tests = num_tests
        self.test_case_results = []
        self.system_out = ''
        self.system_err = ''
        self.time = 0.0

    def accumulate(self, r):
        """
        Add results from r to this result
        @param r: results to aggregate with this result
        @type  r: Result
        """
        self.num_errors += r.num_errors
        self.num_failures += r.num_failures
        self.num_tests += r.num_tests
        self.time += r.time
        self.test_case_results.extend(r.test_case_results)
        if r.system_out:
            self.system_out += '\n'+r.system_out
        if r.system_err:
            self.system_err += '\n'+r.system_err

    def add_test_case_result(self, r):
        """
        Add results from a testcase to this result container
        @param r: TestCaseResult
        @type  r: TestCaseResult
        """
        self.test_case_results.append(r)

    def xml(self):
        """
        @return: document as unicode (UTF-8 declared) XML according to Ant JUnit spec
        """
        testsuite = etree.Element('testsuite')
        testsuite.set('tests', str(self.num_tests))
        testsuite.set('failures', str(self.num_failures))
        testsuite.set('time', str(self.time))
        testsuite.set('errors', str(self.num_errors))
        testsuite.set('name', self.name)
        for tc in self.test_case_results:
            tc.xml(testsuite) 
        system_out = etree.SubElement(testsuite, 'system-out')
        system_out.append(CDATA(self.system_out))
        system_err = etree.SubElement(testsuite, 'system-err')
        system_err.append(CDATA(self.system_err))
        return etree.tostring(testsuite, encoding='utf-8')

def _text(tag):
    return reduce(lambda x, y: x + y, [c.data for c in tag.childNodes if c.nodeType in [DomNode.TEXT_NODE, DomNode.CDATA_SECTION_NODE]], "").strip()

def _load_suite_results(test_suite_name, test_suite, result):
    nodes = [n for n in test_suite.childNodes \
             if n.nodeType == DomNode.ELEMENT_NODE]
    for node in nodes:
        name = node.tagName
        if name == 'testsuite':
            # for now we flatten this hierarchy
            _load_suite_results(test_suite_name, node, result)
        elif name == 'system-out':
            if _text(node):
                system_out = "[%s] stdout"%test_suite_name + "-"*(71-len(test_suite_name))
                system_out += '\n'+_text(node)
                result.system_out += system_out
        elif name == 'system-err':
            if _text(node):
                system_err = "[%s] stderr"%test_suite_name + "-"*(71-len(test_suite_name))
                system_err += '\n'+_text(node)
                result.system_err += system_err
        elif name == 'testcase':
            name = node.getAttribute('name') or 'unknown'
            classname = node.getAttribute('classname') or 'unknown'

            # mangle the classname for some sense of uniformity
            # between rostest/unittest/gtest
            if '__main__.' in classname:
              classname = classname[classname.find('__main__.')+9:]
            if classname == 'rostest.rostest.RosTest':
              classname = 'rostest'
            elif not classname.startswith(result.name):
              classname = "%s.%s"%(result.name,classname)
              
            time = float(node.getAttribute('time')) or 0.0
            tc_result = TestCaseResult("%s/%s"%(test_suite_name,name))
            tc_result.classname = classname
            tc_result.time = time            
            result.add_test_case_result(tc_result)
            for d in [n for n in node.childNodes \
                      if n.nodeType == DomNode.ELEMENT_NODE]:
                # convert 'message' attributes to text elements to keep
                # python unittest and gtest consistent
                if d.tagName == 'failure':
                    message = d.getAttribute('message') or ''
                    text = _text(d) or message
                    x = TestFailure(d.getAttribute('type') or '', text)
                    tc_result.add_failure(x)
                elif d.tagName == 'error':
                    message = d.getAttribute('message') or ''
                    text = _text(d) or message                    
                    x = TestError(d.getAttribute('type') or '', text)
                    tc_result.add_error(x)

## #603: unit test suites are not good about screening out illegal
## unicode characters. This little recipe I from http://boodebr.org/main/python/all-about-python-and-unicode#UNI_XML
## screens these out
RE_XML_ILLEGAL = u'([\u0000-\u0008\u000b-\u000c\u000e-\u001f\ufffe-\uffff])' + \
                 u'|' + \
                 u'([%s-%s][^%s-%s])|([^%s-%s][%s-%s])|([%s-%s]$)|(^[%s-%s])' % \
                 (unichr(0xd800),unichr(0xdbff),unichr(0xdc00),unichr(0xdfff),
                  unichr(0xd800),unichr(0xdbff),unichr(0xdc00),unichr(0xdfff),
                  unichr(0xd800),unichr(0xdbff),unichr(0xdc00),unichr(0xdfff))
_safe_xml_regex = re.compile(RE_XML_ILLEGAL)

def _read_file_safe_xml(test_file, write_back_sanitized=True):
    """
    read in file, screen out unsafe unicode characters
    """
    f = None
    try:
        # this is ugly, but the files in question that are problematic
        # do not declare unicode type.
        if not os.path.isfile(test_file):
            raise Exception("test file does not exist")
        try:
            f = codecs.open(test_file, "r", "utf-8" )
            x = f.read()
        except:
            if f is not None:
                f.close()
            f = codecs.open(test_file, "r", "iso8859-1" )
            x = f.read()        

        for match in _safe_xml_regex.finditer(x):
            x = x[:match.start()] + "?" + x[match.end():]
        x = x.encode("utf-8")
        if write_back_sanitized:
            with open(test_file, 'w') as h:
                h.write(x)
        return x
    finally:
        if f is not None:
            f.close()

def read(test_file, test_name):
    """
    Read in the test_result file
    @param test_file: test file path
    @type  test_file: str
    @param test_name: name of test                    
    @type  test_name: str
    @return: test results
    @rtype: Result
    """
    try:
        xml_str = _read_file_safe_xml(test_file)
        if not xml_str.strip():
            print("WARN: test result file is empty [%s]"%(test_file))
            return Result(test_name, 0, 0, 0)
        test_suites = parseString(xml_str).getElementsByTagName('testsuite')
    except Exception as e:
        print("WARN: cannot read test result file [%s]: %s"%(test_file, str(e)))
        return Result(test_name, 0, 0, 0)
    if not test_suites:
        print("WARN: test result file [%s] contains no results"%(test_file))
        return Result(test_name, 0, 0, 0)

    results = Result(test_name, 0, 0, 0)
    for index, test_suite in enumerate(test_suites):
        # skip test suites which are already covered by a parent test suite
        if index > 0 and test_suite.parentNode in test_suites[0:index]:
            continue

        #test_suite = test_suite[0]
        vals = [test_suite.getAttribute(attr) for attr in ['errors', 'failures', 'tests']]
        vals = [v or 0 for v in vals]
        err, fail, tests = [string.atoi(val) for val in vals]

        result = Result(test_name, err, fail, tests)
        result.time = 0.0 if not len(test_suite.getAttribute('time')) else float(test_suite.getAttribute('time'))

        # Create a prefix based on the test result filename. The idea is to
        # disambiguate the case when tests of the same name are provided in
        # different .xml files.  We use the name of the parent directory
        test_file_base = os.path.basename(os.path.dirname(os.path.abspath(test_file)))
        fname = os.path.basename(test_file)
        if fname.startswith('TEST-'):
            fname = fname[5:]
        if fname.endswith('.xml'):
            fname = fname[:-4]
        test_file_base = "%s.%s"%(test_file_base, fname)
        _load_suite_results(test_file_base, test_suite, result)
        results.accumulate(result)
    return results

def read_all(filter_=[]):
    """
    Read in the test_results and aggregate into a single Result object
    @param filter_: list of packages that should be processed
    @type filter_: [str]
    @return: aggregated result
    @rtype: L{Result}
    """
    dir_ = rospkg.get_test_results_dir()
    root_result = Result('ros', 0, 0, 0)
    if not os.path.exists(dir_):
        return root_result
    for d in os.listdir(dir_):
        if filter_ and not d in filter_:
            continue
        subdir = os.path.join(dir_, d)
        if os.path.isdir(subdir):
            for filename in os.listdir(subdir):
                if filename.endswith('.xml'):
                    filename = os.path.join(subdir, filename)
                    result = read(filename, os.path.basename(subdir))
                    root_result.accumulate(result)
    return root_result


def test_failure_junit_xml(test_name, message, stdout=None):
    """
    Generate JUnit XML file for a unary test suite where the test failed
    
    @param test_name: Name of test that failed
    @type  test_name: str
    @param message: failure message
    @type  message: str
    @param stdout: stdout data to include in report
    @type  stdout: str
    """
    testsuite = etree.Element('testsuite')
    testsuite.set('tests', '1')
    testsuite.set('failures', '1')
    testsuite.set('time', '1')
    testsuite.set('errors', '0')
    testsuite.set('name', test_name)
    testcase = etree.Subelement(testsuite, 'testcase')
    testcase.set('name', 'test_ran')
    testcase.set('status', 'run')
    testcase.set('time', '1')
    testcase.set('classname', 'Results')
    failure = etree.SubElement(testcase, 'failure')
    failure.set('message', message)
    failure.set('type', '')
    if stdout:
        system_out = etree.SubElement(testsuite, 'system-out')
        system_out.append(CDATA(stdout))
    return etree.tostring(testsuite, encoding='utf8')

def test_success_junit_xml(test_name):
    """
    Generate JUnit XML file for a unary test suite where the test succeeded.
    
    @param test_name: Name of test that passed
    @type  test_name: str
    """
    testsuite = etree.Element('testsuite')
    testsuite.set('tests', '1')
    testsuite.set('failures', '0')
    testsuite.set('time', '1')
    testsuite.set('errors', '0')
    testsuite.set('name', test_name)
    testcase = etree.Subelement(testsuite, 'testcase')
    testcase.set('name', 'test_ran')
    testcase.set('status', 'run')
    testcase.set('time', '1')
    testcase.set('classname', 'Results')
    return etree.tostring(testsuite, encoding='utf8', method='xml', xml_declaration=True, pretty_print=True)

def print_summary(junit_results, runner_name='ROSUNIT'):
    """
    Print summary of junitxml results to stdout.
    """
    # we have two separate result objects, which can be a bit
    # confusing. 'result' counts successful _running_ of tests
    # (i.e. doesn't check for actual test success). The 'r' result
    # object contains results of the actual tests.
    
    buff = cStringIO.StringIO()
    buff.write("[%s]"%runner_name+'-'*71+'\n\n')
    for tc_result in junit_results.test_case_results:
        buff.write(tc_result.description)

    buff.write('\nSUMMARY\n')
    if (junit_results.num_errors + junit_results.num_failures) == 0:
        buff.write("\033[32m * RESULT: SUCCESS\033[0m\n")
    else:
        buff.write("\033[1;31m * RESULT: FAIL\033[0m\n")

    # TODO: still some issues with the numbers adding up if tests fail to launch

    # number of errors from the inner tests, plus add in count for tests
    # that didn't run properly ('result' object).
    buff.write(" * TESTS: %s\n"%junit_results.num_tests)
    num_errors = junit_results.num_errors
    if num_errors:
        buff.write("\033[1;31m * ERRORS: %s\033[0m\n"%num_errors)
    else:
        buff.write(" * ERRORS: 0\n")
    num_failures = junit_results.num_failures
    if num_failures:
        buff.write("\033[1;31m * FAILURES: %s\033[0m\n"%num_failures)
    else:
        buff.write(" * FAILURES: 0\n")

    print(buff.getvalue())

