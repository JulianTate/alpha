import sqlite3
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.registry import (ensure_registry_tables, create_campaign, create_experiment,
                               transition_campaign, register_strategy_genome, list_strategy_genomes)

class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:')
        ensure_registry_tables(self.c)
    def test_campaign_and_experiment_are_deterministic_and_immutable(self):
        definition={'research_question':'Does baseline momentum survive costs?','dataset_id':'DS-123','universe':['AAPL'],'train_period':['2018','2022'],'validation_period':['2022','2024'],'test_period':['2024','2025']}
        campaign=create_campaign(self.c,definition)
        self.assertTrue(campaign['campaign_id'].startswith('CAM-'))
        experiment=create_experiment(self.c,campaign['campaign_id'],{'strategy_version':'baseline-v1','parameters':{'lookback':20},'dataset_id':'DS-123','cost_model':{'fee_bps':1},'slippage_model':{'bps':5},'engine_version':'engine-v1'})
        self.assertTrue(experiment['experiment_id'].startswith('EXP-'))
        with self.assertRaises(sqlite3.IntegrityError): create_campaign(self.c,definition)
    def test_strategy_genome_is_deterministic_immutable_and_lineaged(self):
        definition={'strategy_name':'cost-aware momentum','family':'MOMENTUM','parameters':{'lookback':20},'feature_definition':{'price':'close'},'signal_definition':{'rule':'return>0'},'cost_model':{'bps':5}}
        first=register_strategy_genome(self.c,definition)
        second=register_strategy_genome(self.c,definition)
        self.assertEqual(first['genome_id'],second['genome_id'])
        child=register_strategy_genome(self.c,{**definition,'parameters':{'lookback':50}},first['genome_id'])
        self.assertEqual(child['parent_genome_id'],first['genome_id'])
        self.assertEqual(len(list_strategy_genomes(self.c)),2)
        changed=register_strategy_genome(self.c,{**definition,'parameters':{'lookback':99}},first['genome_id'])
        self.assertNotEqual(changed['genome_id'],first['genome_id'])
        self.assertEqual(changed['parent_genome_id'],first['genome_id'])

    def test_strategy_genome_requires_existing_parent(self):
        definition={'strategy_name':'x','family':'TREND','parameters':{},'feature_definition':{},'signal_definition':{},'cost_model':{'bps':1}}
        with self.assertRaises(ValueError): register_strategy_genome(self.c,definition,'GEN-NOTFOUND')

    def test_invalid_state_rejected(self):
        definition={'research_question':'q','dataset_id':'DS-123','universe':['AAPL'],'train_period':['2018','2022'],'validation_period':['2022','2024'],'test_period':['2024','2025']}
        campaign=create_campaign(self.c,definition)
        with self.assertRaises(ValueError): transition_campaign(self.c,campaign['campaign_id'],'DONE')

if __name__=='__main__': unittest.main()
