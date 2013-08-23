# -*- coding: utf-8 -*-

############################ Copyrights and license ############################
#                                                                              #
# Copyright 2012 Vincent Jacques <vincent@vincent-jacques.net>                 #
# Copyright 2012 Zearin <zearin@gonk.net>                                      #
# Copyright 2013 AKFish <akfish@gmail.com>                                     #
# Copyright 2013 Vincent Jacques <vincent@vincent-jacques.net>                 #
#                                                                              #
# This file is part of PyGithub. http://jacquev6.github.com/PyGithub/          #
#                                                                              #
# PyGithub is free software: you can redistribute it and/or modify it under    #
# the terms of the GNU Lesser General Public License as published by the Free  #
# Software Foundation, either version 3 of the License, or (at your option)    #
# any later version.                                                           #
#                                                                              #
# PyGithub is distributed in the hope that it will be useful, but WITHOUT ANY  #
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS    #
# FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License for more #
# details.                                                                     #
#                                                                              #
# You should have received a copy of the GNU Lesser General Public License     #
# along with PyGithub. If not, see <http://www.gnu.org/licenses/>.             #
#                                                                              #
################################################################################

from __future__ import with_statement

import datetime
import pickle

import GithubException
import Consts


class _NotSetType:
    def __repr__(self):
        return "NotSet"
NotSet = _NotSetType()


class GithubObject(object):
    """
    Base class for all classes representing objects returned by the API.
    """

    '''
    A global debug flag to enable header validation by requester for all objects
    '''
    CHECK_AFTER_INIT_FLAG = False

    @classmethod
    def setCheckAfterInitFlag(cls, flag):
        cls.CHECK_AFTER_INIT_FLAG = flag

    def __init__(self, requester, headers, attributes, completed):
        self._requester = requester
        self._initAttributes()
        self._storeAndUseAttributes(headers, attributes)

        # Ask requester to do some checking, for debug and test purpose
        # Since it's most handy to access and kinda all-knowing
        if self.CHECK_AFTER_INIT_FLAG:  # pragma no branch (Flag always set in tests)
            requester.check_me(self)

    def _storeAndUseAttributes(self, headers, attributes):
        # Make sure headers are assigned before calling _useAttributes
        # (Some derived classes will use headers in _useAttributes)
        self._headers = headers
        self._rawData = attributes
        self._useAttributes(attributes)

    @property
    def raw_data(self):
        """
        :type: dict
        """
        self._completeIfNeeded()
        return self._rawData

    @staticmethod
    def _parentUrl(url):
        return "/".join(url.split("/")[: -1])

    @staticmethod
    def _NoneIfNotSet(value):
        if value is NotSet:
            return None
        else:
            return value

    @staticmethod
    def _parseDatetime(s):
        if s is None:
            return None
        elif len(s) == 24:
            return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.000Z")
        elif len(s) == 25:
            return datetime.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S") + (1 if s[19] == '-' else -1) * datetime.timedelta(hours=int(s[20:22]), minutes=int(s[23:25]))
        else:
            return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")

    # #193: I temporarily comment out those two methods
    # We need to address the following:
    #  - The interface should use file-like objects (not file names)
    #    - it's more "pythonic"
    #    - it allows user to save several objects in the same physical file
    #    - it's easier to unit-test because we can inject in-memory file-like objects
    #  - We should not save identification information
    #  - We should not re-create several instances of Requester when loading objects
    #    - This would lead to very surprising behaviors, when changing Github.per_page or anything impacting this central part of PyGithub
    #  - It should be possible to restore a saved object without knowing its previous type
    #  - The "load" method should not make the user think she must know this previous type
    #    - In particular, it shouldn't be a classmethod of GithubObject
    #  - They should be covered by unit tests
    #
    # My proposal, to be experimented and discussed:
    #  - in "save", pickle a tuple containing the class of the object, its rawData and its headers
    #  - make "load" a method of class Github
    #  - it will unpickle everything and call Github.create_from_raw_data
    #  - I would even make "save" a method of Github, to keep it symetric with "load"
    #
    # Using __get_state__ would not be enought because we wouldn't have access
    # to the Requester instance in __set_state__.

    # def save(self, file_name):
    #     '''
    #     Save instance to a file
    #     :param file_name: the full path of target file
    #     '''
    #     with open(file_name, 'wb') as f:
    #         pickle.dump(self, f)

    # @classmethod
    # def load(cls, file_name):
    #     '''
    #     Load saved instance from file
    #     :param file_name: the full path to saved file
    #     :rtype: saved instance. The type of loaded instance remains its orginal one and will not be affected by from which derived class the method is called.
    #     '''
    #     with open(file_name, 'rb') as f:
    #         return pickle.load(f)

    @property
    def etag(self):
        '''
        :type str
        '''
        return self._headers.get(Consts.RES_ETAG)

    @property
    def last_modified(self):
        '''
        :type str
        '''
        return self._headers.get(Consts.RES_LAST_MODIFED)


class NonCompletableGithubObject(GithubObject):
    def _completeIfNeeded(self):
        pass


class CompletableGithubObject(GithubObject):
    def __init__(self, requester, headers, attributes, completed):
        GithubObject.__init__(self, requester, headers, attributes, completed)
        self.__completed = completed

    def _completeIfNotSet(self, value):
        if value is NotSet:
            self._completeIfNeeded()

    def _completeIfNeeded(self):
        if not self.__completed:
            self.__complete()

    def __complete(self):
        headers, data = self._requester.requestJsonAndCheck(
            "GET",
            self._url,
            None,
            None,
            None
        )
        self._storeAndUseAttributes(headers, data)
        self.__completed = True

    def update(self):
        '''
        Check and update the object with conditional request
        :rtype: Boolean value indicating whether the object is changed
        '''
        conditionalRequestHeader = dict()
        if self.etag is not None:
            conditionalRequestHeader[Consts.REQ_IF_NONE_MATCH] = self.etag
        if self.last_modified is not None:
            conditionalRequestHeader[Consts.REQ_IF_MODIFIED_SINCE] = self.last_modified

        status, responseHeaders, output = self._requester.requestJson(
            "GET",
            self._url,
            None,
            conditionalRequestHeader,
            None
        )
        if status == 304:
            return False
        else:
            headers, data = self._requester._Requester__check(status, responseHeaders, output)
            self._storeAndUseAttributes(headers, data)
            self.__completed = True
            return True
