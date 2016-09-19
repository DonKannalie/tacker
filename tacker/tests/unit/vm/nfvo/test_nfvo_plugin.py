# Copyright 2016 Brocade Communications System, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock
import uuid


from mock import patch
from tacker import context
from tacker.db.common_services import common_services_db
from tacker.db.nfvo import nfvo_db
from tacker.db.nfvo import vnffg_db
from tacker.extensions import nfvo
from tacker.manager import TackerManager
from tacker.nfvo import nfvo_plugin
from tacker.plugins.common import constants
from tacker.tests.unit.db import base as db_base
from tacker.tests.unit.db import utils

SECRET_PASSWORD = '***'


def dummy_get_vim(*args, **kwargs):
    vim_auth = utils.get_vim_auth_obj()
    vim_auth['type'] = 'openstack'
    return vim_auth


class FakeDriverManager(mock.Mock):
    def invoke(self, *args, **kwargs):
        if any(x in ['create', 'create_chain', 'create_flow_classifier'] for
               x in args):
            return str(uuid.uuid4())


class FakeVNFMPlugin(mock.Mock):

    def __init__(self):
        super(FakeVNFMPlugin, self).__init__()
        self.vnf1_vnfd_id = 'eb094833-995e-49f0-a047-dfb56aaf7c4e'
        self.vnf1_vnf_id = '91e32c20-6d1f-47a4-9ba7-08f5e5effe07'
        self.vnf3_vnfd_id = 'e4015e9f-1ef2-49fb-adb6-070791ad3c45'
        self.vnf3_vnf_id = '7168062e-9fa1-4203-8cb7-f5c99ff3ee1b'
        self.vnf3_update_vnf_id = '10f66bc5-b2f1-45b7-a7cd-6dd6ad0017f5'

        self.cp11_id = 'd18c8bae-898a-4932-bff8-d5eac981a9c9'
        self.cp12_id = 'c8906342-3e30-4b2a-9401-a251a7a9b5dd'
        self.cp32_id = '3d1bd2a2-bf0e-44d1-87af-a2c6b2cad3ed'
        self.cp32_update_id = '064c0d99-5a61-4711-9597-2a44dc5da14b'

    def get_vnfds(self, *args, **kwargs):
        if {'name': ['VNF1']} in args:
            return [{'id': self.vnf1_vnfd_id}]
        elif {'name': ['VNF3']} in args:
            return [{'id': self.vnf3_vnfd_id}]
        else:
            return None

    def get_vnfs(self, *args, **kwargs):
        if {'vnfd_id': [self.vnf1_vnfd_id]} in args:
            return [{'id': self.vnf1_vnf_id}]
        elif {'vnfd_id': [self.vnf3_vnfd_id]} in args:
            return [{'id': self.vnf3_vnf_id}]
        else:
            return None

    def get_vnf(self, *args, **kwargs):
        if self.vnf1_vnf_id in args:
            return self.get_dummy_vnf1()
        elif self.vnf3_vnf_id in args:
            return self.get_dummy_vnf3()
        elif self.vnf3_update_vnf_id in args:
            return self.get_dummy_vnf3_update()

    def get_vnf_resources(self, *args, **kwargs):
        if self.vnf1_vnf_id in args:
            return self.get_dummy_vnf1_details()
        elif self.vnf3_vnf_id in args:
            return self.get_dummy_vnf3_details()
        elif self.vnf3_update_vnf_id in args:
            return self.get_dummy_vnf3_update_details()

    def get_dummy_vnf1_details(self):
        return [{'name': 'CP11', 'id': self.cp11_id},
                {'name': 'CP12', 'id': self.cp12_id}]

    def get_dummy_vnf3_details(self):
        return [{'name': 'CP32', 'id': self.cp32_id}]

    def get_dummy_vnf3_update_details(self):
        return [{'name': 'CP32', 'id': self.cp32_update_id}]

    def get_dummy_vnf1(self):
        return {'description': 'dummy_vnf_description',
                'vnfd_id': self.vnf1_vnfd_id,
                'vim_id': u'6261579e-d6f3-49ad-8bc3-a9cb974778ff',
                'tenant_id': u'ad7ebc56538745a08ef7c5e97f8bd437',
                'name': 'dummy_vnf1',
                'attributes': {}}

    def get_dummy_vnf3(self):
        return {'description': 'dummy_vnf_description',
                'vnfd_id': self.vnf3_vnfd_id,
                'vim_id': u'6261579e-d6f3-49ad-8bc3-a9cb974778ff',
                'tenant_id': u'ad7ebc56538745a08ef7c5e97f8bd437',
                'name': 'dummy_vnf2',
                'attributes': {}}

    def get_dummy_vnf3_update(self):
        return {'description': 'dummy_vnf_description',
                'vnfd_id': self.vnf3_vnfd_id,
                'vim_id': u'6261579e-d6f3-49ad-8bc3-a9cb974778ff',
                'tenant_id': u'ad7ebc56538745a08ef7c5e97f8bd437',
                'name': 'dummy_vnf_update',
                'attributes': {}}


class TestNfvoPlugin(db_base.SqlTestCase):
    def setUp(self):
        super(TestNfvoPlugin, self).setUp()
        self.addCleanup(mock.patch.stopall)
        self.context = context.get_admin_context()
        self._mock_driver_manager()
        mock.patch('tacker.nfvo.nfvo_plugin.NfvoPlugin.__run__').start()
        mock.patch('tacker.nfvo.nfvo_plugin.NfvoPlugin._get_vim_from_vnf',
                   side_effect=dummy_get_vim).start()
        self.nfvo_plugin = nfvo_plugin.NfvoPlugin()
        mock.patch('tacker.db.common_services.common_services_db.'
                   'CommonServicesPluginDb.create_event'
                   ).start()
        self._cos_db_plugin = common_services_db.CommonServicesPluginDb()

    def _mock_driver_manager(self):
        self._driver_manager = mock.Mock(wraps=FakeDriverManager())
        self._driver_manager.__contains__ = mock.Mock(
            return_value=True)
        fake_driver_manager = mock.Mock()
        fake_driver_manager.return_value = self._driver_manager
        self._mock(
            'tacker.common.driver_manager.DriverManager', fake_driver_manager)

    def _insert_dummy_vim(self):
        session = self.context.session
        vim_db = nfvo_db.Vim(
            id='6261579e-d6f3-49ad-8bc3-a9cb974778ff',
            tenant_id='ad7ebc56538745a08ef7c5e97f8bd437',
            name='fake_vim',
            description='fake_vim_description',
            type='openstack',
            status='Active',
            placement_attr={'regions': ['RegionOne']})
        vim_auth_db = nfvo_db.VimAuth(
            vim_id='6261579e-d6f3-49ad-8bc3-a9cb974778ff',
            password='encrypted_pw',
            auth_url='http://localhost:5000',
            vim_project={'name': 'test_project'},
            auth_cred={'username': 'test_user', 'user_domain_id': 'default',
                       'project_domain_d': 'default'})
        session.add(vim_db)
        session.add(vim_auth_db)
        session.flush()

    def test_create_vim(self):
        vim_dict = {'vim': {'type': 'openstack', 'auth_url':
                    'http://localhost:5000', 'vim_project': {'name':
                    'test_project'}, 'auth_cred': {'username': 'test_user',
                                                   'password':
                                                       'test_password'},
                            'name': 'VIM0',
                    'tenant_id': 'test-project'}}
        vim_type = 'openstack'
        res = self.nfvo_plugin.create_vim(self.context, vim_dict)
        self._cos_db_plugin.create_event.assert_any_call(
            self.context, evt_type=constants.RES_EVT_CREATE, res_id=mock.ANY,
            res_state=mock.ANY, res_type=constants.RES_TYPE_VIM,
            tstamp=mock.ANY)
        self._cos_db_plugin.create_event.assert_any_call(
            mock.ANY, evt_type=constants.RES_EVT_MONITOR, res_id=mock.ANY,
            res_state=mock.ANY, res_type=constants.RES_TYPE_VIM,
            tstamp=mock.ANY)
        self._driver_manager.invoke.assert_any_call(vim_type,
            'register_vim', vim_obj=vim_dict['vim'])
        self._driver_manager.invoke.assert_any_call('openstack', 'vim_status',
            auth_url='http://localhost:5000')
        self.assertIsNotNone(res)
        self.assertEqual(SECRET_PASSWORD, res['auth_cred']['password'])
        self.assertIn('id', res)
        self.assertIn('placement_attr', res)
        self.assertIn('created_at', res)
        self.assertIn('updated_at', res)

    def test_delete_vim(self):
        self._insert_dummy_vim()
        vim_type = 'openstack'
        vim_id = '6261579e-d6f3-49ad-8bc3-a9cb974778ff'
        self.nfvo_plugin.delete_vim(self.context, vim_id)
        self._driver_manager.invoke.assert_called_once_with(vim_type,
                                                            'deregister_vim',
                                                            vim_id=vim_id)
        self._cos_db_plugin.create_event.assert_called_with(
            self.context, evt_type=constants.RES_EVT_DELETE, res_id=mock.ANY,
            res_state=mock.ANY, res_type=constants.RES_TYPE_VIM,
            tstamp=mock.ANY)

    def test_update_vim(self):
        vim_dict = {'vim': {'id': '6261579e-d6f3-49ad-8bc3-a9cb974778ff',
                            'vim_project': {'name': 'new_project'},
                            'auth_cred': {'username': 'new_user',
                                          'password': 'new_password'}}}
        vim_type = 'openstack'
        vim_auth_username = vim_dict['vim']['auth_cred']['username']
        vim_project = vim_dict['vim']['vim_project']
        self._insert_dummy_vim()
        res = self.nfvo_plugin.update_vim(self.context, vim_dict['vim']['id'],
                                          vim_dict)
        self._driver_manager.invoke.assert_called_once_with(vim_type,
                                                            'register_vim',
                                                            vim_obj=mock.ANY)
        self.assertIsNotNone(res)
        self.assertIn('id', res)
        self.assertIn('placement_attr', res)
        self.assertEqual(vim_project, res['vim_project'])
        self.assertEqual(vim_auth_username, res['auth_cred']['username'])
        self.assertEqual(SECRET_PASSWORD, res['auth_cred']['password'])
        self.assertIn('updated_at', res)
        self._cos_db_plugin.create_event.assert_called_with(
            self.context, evt_type=constants.RES_EVT_UPDATE, res_id=mock.ANY,
            res_state=mock.ANY, res_type=constants.RES_TYPE_VIM,
            tstamp=mock.ANY)

    def _insert_dummy_vnffg_template(self):
        session = self.context.session
        vnffg_template = vnffg_db.VnffgTemplate(
            id='eb094833-995e-49f0-a047-dfb56aaf7c4e',
            tenant_id='ad7ebc56538745a08ef7c5e97f8bd437',
            name='fake_template',
            description='fake_template_description',
            template={u'vnffgd': utils.vnffgd_tosca_template})
        session.add(vnffg_template)
        session.flush()
        return vnffg_template

    def _insert_dummy_vnffg(self):
        session = self.context.session
        vnffg = vnffg_db.Vnffg(
            id='ffc1a59b-65bb-4874-94d3-84f639e63c74',
            tenant_id='ad7ebc56538745a08ef7c5e97f8bd437',
            name='dummy_vnffg',
            description="fake vnffg",
            vnffgd_id='eb094833-995e-49f0-a047-dfb56aaf7c4e',
            status='ACTIVE',
            vnf_mapping={'VNF1': '91e32c20-6d1f-47a4-9ba7-08f5e5effe07',
                         'VNF3': '7168062e-9fa1-4203-8cb7-f5c99ff3ee1b'})
        session.add(vnffg)
        nfp = vnffg_db.VnffgNfp(
            id='768f76a7-9025-4acd-b51c-0da609759983',
            tenant_id='ad7ebc56538745a08ef7c5e97f8bd437',
            status="ACTIVE",
            name='Forwarding_path1',
            vnffg_id='ffc1a59b-65bb-4874-94d3-84f639e63c74',
            path_id=51,
            symmetrical=False)
        session.add(nfp)
        sfc = vnffg_db.VnffgChain(
            id='f28e33bc-1061-4762-b942-76060bbd59c4',
            tenant_id='ad7ebc56538745a08ef7c5e97f8bd437',
            symmetrical=False,
            chain=[{'connection_points': [
                'd18c8bae-898a-4932-bff8-d5eac981a9c9',
                'c8906342-3e30-4b2a-9401-a251a7a9b5dd'],
                'name': 'dummy_vnf1'},
                {'connection_points': ['3d1bd2a2-bf0e-44d1-87af-a2c6b2cad3ed'],
                 'name': 'dummy_vnf2'}],
            path_id=51,
            status='ACTIVE',
            nfp_id='768f76a7-9025-4acd-b51c-0da609759983',
            instance_id='bcfb295e-578e-405b-a349-39f06b25598c')
        session.add(sfc)
        fc = vnffg_db.VnffgClassifier(
            id='a85f21b5-f446-43f0-86f4-d83bdc5590ab',
            tenant_id='ad7ebc56538745a08ef7c5e97f8bd437',
            status='ACTIVE',
            instance_id='3007dc2d-30dc-4651-9184-f1e6273cc0b6',
            chain_id='f28e33bc-1061-4762-b942-76060bbd59c4',
            nfp_id='768f76a7-9025-4acd-b51c-0da609759983')
        session.add(fc)
        match = vnffg_db.ACLMatchCriteria(
            id='bdb0f2db-d4c2-42a2-a1df-426079ecc443',
            vnffgc_id='a85f21b5-f446-43f0-86f4-d83bdc5590ab',
            eth_src=None, eth_dst=None, eth_type=None, vlan_id=None,
            vlan_pcp=None, mpls_label=None, mpls_tc=None, ip_dscp=None,
            ip_ecn=None, ip_src_prefix=None, ip_dst_prefix='192.168.1.2/24',
            source_port_min=None, source_port_max=None,
            destination_port_min=80, destination_port_max=1024, ip_proto=6,
            network_id=None, network_src_port_id=None,
            network_dst_port_id=None, tenant_id=None, icmpv4_type=None,
            icmpv4_code=None, arp_op=None, arp_spa=None, arp_tpa=None,
            arp_sha=None, arp_tha=None, ipv6_src=None, ipv6_dst=None,
            ipv6_flabel=None, icmpv6_type=None, icmpv6_code=None,
            ipv6_nd_target=None, ipv6_nd_sll=None, ipv6_nd_tll=None)
        session.add(match)
        session.flush()
        return vnffg

    def test_validate_tosca(self):
        template = utils.vnffgd_tosca_template
        self.nfvo_plugin.validate_tosca(template)

    def test_validate_tosca_missing_tosca_ver(self):
        template = utils.vnffgd_template
        self.assertRaises(nfvo.ToscaParserFailed,
                          self.nfvo_plugin.validate_tosca,
                          template)

    def test_validate_tosca_invalid(self):
        template = utils.vnffgd_invalid_tosca_template
        self.assertRaises(nfvo.ToscaParserFailed,
                          self.nfvo_plugin.validate_tosca,
                          template)

    def test_create_vnffgd(self):
        vnffgd_obj = utils.get_dummy_vnffgd_obj()
        result = self.nfvo_plugin.create_vnffgd(self.context, vnffgd_obj)
        self.assertIsNotNone(result)
        self.assertIn('id', result)
        self.assertIn('template', result)

    def test_create_vnffg_abstract_types(self):
        with patch.object(TackerManager, 'get_service_plugins') as \
                mock_plugins:
            mock_plugins.return_value = {'VNFM': FakeVNFMPlugin()}
            mock.patch('tacker.common.driver_manager.DriverManager',
                       side_effect=FakeDriverManager()).start()
            self._insert_dummy_vnffg_template()
            vnffg_obj = utils.get_dummy_vnffg_obj()
            result = self.nfvo_plugin.create_vnffg(self.context, vnffg_obj)
            self.assertIsNotNone(result)
            self.assertIn('id', result)
            self.assertIn('status', result)
            self.assertEqual('PENDING_CREATE', result['status'])
            self._driver_manager.invoke.assert_called_with(mock.ANY, mock.ANY,
                                                           vnfs=mock.ANY,
                                                           fc_id=mock.ANY,
                                                           auth_attr=mock.ANY,
                                                           symmetrical=mock.ANY
                                                           )

    def test_create_vnffg_vnf_mapping(self):
        with patch.object(TackerManager, 'get_service_plugins') as \
                mock_plugins:
            mock_plugins.return_value = {'VNFM': FakeVNFMPlugin()}
            mock.patch('tacker.common.driver_manager.DriverManager',
                       side_effect=FakeDriverManager()).start()
            self._insert_dummy_vnffg_template()
            vnffg_obj = utils.get_dummy_vnffg_obj_vnf_mapping()
            result = self.nfvo_plugin.create_vnffg(self.context, vnffg_obj)
            self.assertIsNotNone(result)
            self.assertIn('id', result)
            self.assertIn('status', result)
            self.assertEqual('PENDING_CREATE', result['status'])
            self._driver_manager.invoke.assert_called_with(mock.ANY, mock.ANY,
                                                           vnfs=mock.ANY,
                                                           fc_id=mock.ANY,
                                                           auth_attr=mock.ANY,
                                                           symmetrical=mock.ANY
                                                           )

    def test_update_vnffg_nonexistent_vnf(self):
        with patch.object(TackerManager, 'get_service_plugins') as \
                mock_plugins:
            mock_plugins.return_value = {'VNFM': FakeVNFMPlugin()}
            mock.patch('tacker.common.driver_manager.DriverManager',
                       side_effect=FakeDriverManager()).start()
            self._insert_dummy_vnffg_template()
            vnffg = self._insert_dummy_vnffg()
            updated_vnffg = utils.get_dummy_vnffg_obj_vnf_mapping()
            updated_vnffg['vnffg']['symmetrical'] = True
            updated_vnf_mapping = \
                {'VNF1': '91e32c20-6d1f-47a4-9ba7-08f5e5effe07',
                 'VNF3': '5c7f5631-9e74-46e8-b3d2-397c0eda9d0b'}
            updated_vnffg['vnffg']['vnf_mapping'] = updated_vnf_mapping
            self.assertRaises(nfvo.VnffgInvalidMappingException,
                              self.nfvo_plugin.update_vnffg,
                              self.context, vnffg['id'], updated_vnffg)

    def test_update_vnffg(self):
        with patch.object(TackerManager, 'get_service_plugins') as \
                mock_plugins:
            mock_plugins.return_value = {'VNFM': FakeVNFMPlugin()}
            mock.patch('tacker.common.driver_manager.DriverManager',
                       side_effect=FakeDriverManager()).start()
            self._insert_dummy_vnffg_template()
            vnffg = self._insert_dummy_vnffg()
            updated_vnffg = utils.get_dummy_vnffg_obj_vnf_mapping()
            updated_vnffg['vnffg']['symmetrical'] = True
            updated_vnf_mapping = \
                {'VNF1': '91e32c20-6d1f-47a4-9ba7-08f5e5effe07',
                 'VNF3': '10f66bc5-b2f1-45b7-a7cd-6dd6ad0017f5'}
            updated_vnffg['vnffg']['vnf_mapping'] = updated_vnf_mapping
            self.nfvo_plugin.update_vnffg(self.context, vnffg['id'],
                                          updated_vnffg)
            self._driver_manager.invoke.assert_called_with(mock.ANY, mock.ANY,
                                                           vnfs=mock.ANY,
                                                           fc_ids=mock.ANY,
                                                           chain_id=mock.ANY,
                                                           auth_attr=mock.ANY,
                                                           symmetrical=True)

    def test_delete_vnffg(self):
        self._insert_dummy_vnffg_template()
        vnffg = self._insert_dummy_vnffg()
        self.nfvo_plugin.delete_vnffg(self.context, vnffg['id'])
        self._driver_manager.invoke.assert_called_with(mock.ANY, mock.ANY,
                                                       fc_id=mock.ANY,
                                                       auth_attr=mock.ANY)
