"""Regression checks for controls; all evidence here is TEST DATA, never live output."""
import unittest,tempfile,json,sys,copy
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from marketplace_service import service as svc
class Boundaries(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.patches=[patch.object(svc,'STATE',Path(self.temp.name)/'store.json'),patch.object(svc,'PROPOSALS',{}),patch.object(svc,'ORDERS',{})]
        for p in self.patches:p.start()
        self.offer={'offer_id':'TEST-ONLY','marketplace':'Amazon','product_name':'TEST Black running shoes','source_excerpt':'TEST ONLY: Black running shoes.','source_url':'https://www.amazon.in/dp/TEST000000','observed_price_inr':999,'observed_at':datetime.now(timezone.utc).isoformat(),'unverified_fields':['checkout_total'],'evidence_mode':'retailer_page'}
        svc.PROPOSALS['test']={'lane':'approval','deterministic_validation':{'passed':True},'selected_offer':copy.deepcopy(self.offer),'parsed_request':{'budget_inr':1000}}
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def test_requires_approval(self):
        with self.assertRaisesRegex(ValueError,'Explicit'):svc.order({'approved':False,'proposal_id':'test','selected_offer':self.offer})
    def test_rejects_changed_proposal(self):
        changed={**self.offer,'observed_price_inr':1}
        with self.assertRaisesRegex(ValueError,'identity'):svc.order({'approved':True,'proposal_id':'test','selected_offer':changed})
    def test_rechecks_expiry(self):
        old=(datetime.now(timezone.utc)-timedelta(minutes=16)).isoformat();svc.PROPOSALS['test']['selected_offer']['observed_at']=old
        with self.assertRaisesRegex(ValueError,'expired'):svc.order({'approved':True,'proposal_id':'test','selected_offer':svc.PROPOSALS['test']['selected_offer']})
    def test_rejects_bad_host_and_budget(self):
        self.assertTrue(svc.check({**self.offer,'source_url':'https://amazon.in.evil.example/x'},1000))
        self.assertTrue(svc.check({**self.offer,'observed_price_inr':1000},1000))
    def test_missing_color_stops(self):
        self.assertTrue(svc.check({**self.offer,'product_name':'Running shoes','source_excerpt':'Blue running shoes'},1000))
    def test_unknown_proposal_stops(self):
        with self.assertRaisesRegex(ValueError,'Unknown'):svc.order({'approved':True,'proposal_id':'missing','selected_offer':self.offer})
if __name__=='__main__':unittest.main()
