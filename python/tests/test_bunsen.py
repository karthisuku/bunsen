import os

from tempfile import mkdtemp
from pytest import fixture

from pyspark.sql import SparkSession
from pyspark.sql.functions import col

from bunsen.mapping.loinc import with_loinc_hierarchy
from bunsen.mapping.snomed import with_relationships
from bunsen.mapping import get_empty_concept_maps, get_default_concept_maps, get_empty_value_sets, get_empty_hierarchies
from bunsen.bundles import load_from_directory, extract_entry, save_as_database, to_bundle
from bunsen.valuesets import push_valuesets, isa_loinc, isa_snomed, get_current_valuesets

import xml.etree.ElementTree as ET

EXPECTED_COLUMNS = {'uri',
                    'version',
                    'descendantSystem',
                    'descendantValue',
                    'ancestorSystem',
                    'ancestorValue'}

@fixture(scope="session")
def spark_session(request):
  """
  Fixture for creating a Spark Session available for all tests in this
  testing session.
  """

  # Get the shaded JAR for testing purposes.
  shaded_jar =  os.environ['SHADED_JAR_PATH']

  spark = SparkSession.builder \
    .appName('Foresight-test') \
    .master('local[2]') \
    .config('spark.jars', shaded_jar) \
    .config('hive.exec.dynamic.partition.mode', 'nonstrict') \
    .config('spark.sql.warehouse.dir', mkdtemp()) \
    .config('javax.jdo.option.ConnectionURL',
            'jdbc:derby:memory:metastore_db;create=true') \
    .enableHiveSupport() \
    .getOrCreate()

  request.addfinalizer(lambda: spark.stop())

  return spark


# Concept Maps Tests
def test_add_map(spark_session):

  concept_maps = get_empty_concept_maps(spark_session)

  snomed_to_loinc = [('http://snomed.info/sct', '75367002', 'http://loinc.org', '55417-0', 'equivalent'), # Blood pressure
                     ('http://snomed.info/sct', '271649006', 'http://loinc.org', '8480-6', 'equivalent'), # Systolic BP
                     ('http://snomed.info/sct', '271650006', 'http://loinc.org', '8462-4', 'equivalent')] # Diastolic BP

  appended = concept_maps.with_new_map(url='urn:cerner:test:snomed-to-loinc',
                                      version='0.1',
                                      source='urn:cerner:test:valueset',
                                      target='http://hl7.org/fhir/ValueSet/observation-code',
                                      mappings=snomed_to_loinc)

  assert appended.get_maps().count() == 1
  assert appended.get_mappings().where(col('conceptmapuri') == 'urn:cerner:test:snomed-to-loinc').count() == 3

def test_get_map_as_xml(spark_session):

  concept_maps = get_empty_concept_maps(spark_session)

  snomed_to_loinc = [('http://snomed.info/sct', '75367002', 'http://loinc.org', '55417-0', 'equivalent'), # Blood pressure
                     ('http://snomed.info/sct', '271649006', 'http://loinc.org', '8480-6', 'equivalent'), # Systolic BP
                     ('http://snomed.info/sct', '271650006', 'http://loinc.org', '8462-4', 'equivalent')] # Diastolic BP

  appended = concept_maps.with_new_map(url='urn:cerner:test:snomed-to-loinc',
                                      version='0.1',
                                      source='urn:cerner:test:valueset',
                                      target='http://hl7.org/fhir/ValueSet/observation-code',
                                      mappings=snomed_to_loinc)

  xml_str = appended.get_map_as_xml('urn:cerner:test:snomed-to-loinc', '0.1')

  root = ET.fromstring(xml_str)
  assert root.tag == '{http://hl7.org/fhir}ConceptMap'

def test_write_maps(spark_session):

  concept_maps = get_empty_concept_maps(spark_session)

  snomed_to_loinc = [('http://snomed.info/sct', '75367002', 'http://loinc.org', '55417-0', 'equivalent'), # Blood pressure
                     ('http://snomed.info/sct', '271649006', 'http://loinc.org', '8480-6', 'equivalent'), # Systolic BP
                     ('http://snomed.info/sct', '271650006', 'http://loinc.org', '8462-4', 'equivalent')] # Diastolic BP

  appended = concept_maps.with_new_map(url='urn:cerner:test:snomed-to-loinc',
                                      version='0.1',
                                      source='urn:cerner:test:valueset',
                                      target='http://hl7.org/fhir/ValueSet/observation-code',
                                      mappings=snomed_to_loinc)

  spark_session.sql('create database if not exists ontologies')
  spark_session.sql('drop table if exists ontologies.mappings')
  spark_session.sql('drop table if exists ontologies.ancestors')
  spark_session.sql('drop table if exists ontologies.conceptmaps')

  appended.write_to_database('ontologies')

  # Check that the maps were written by reloading and inspecting them.
  reloaded = get_default_concept_maps(spark_session)

  assert reloaded.get_maps().count() == 1
  assert reloaded.get_mappings().where(col('conceptmapuri') == 'urn:cerner:test:snomed-to-loinc').count() == 3

# Value Sets Tests
def test_add_valueset(spark_session):

  value_sets = get_empty_value_sets(spark_session)

  values = [('urn:cerner:system1', 'urn:code:a'),
            ('urn:cerner:system1', 'urn:code:b'),
            ('urn:cerner:system2', 'urn:code:1')]

  appended = value_sets.with_new_value_set(url='urn:cerner:test:valuesets:testvalueset',
                                           version='0.1',
                                           values=values)

  assert appended.get_value_sets().count() == 1
  assert appended.get_values().count() == 3

def test_get_value_set_as_xml(spark_session):

  value_sets = get_empty_value_sets(spark_session)

  values = [('urn:cerner:system1', 'urn:code:a'),
            ('urn:cerner:system1', 'urn:code:b'),
            ('urn:cerner:system2', 'urn:code:1')]

  appended = value_sets.with_new_value_set(url='urn:cerner:test:valuesets:testvalueset',
                                           version='0.1',
                                           values=values)
  # this test fails because version is null on line 778 of ValueSets.java
  xml_str = appended.get_value_set_as_xml('urn:cerner:test:valuesets:testvalueset', '0.1')

  root = ET.fromstring(xml_str)
  assert root.tag == '{http://hl7.org/fhir}ValueSet'

# LOINC Tests
def test_read_hierarchy_file(spark_session):
  ancestors = with_loinc_hierarchy(
      spark_session,
      get_empty_hierarchies(spark_session),
      'tests/resources/LOINC_HIERARCHY_SAMPLE.CSV',
      '2.56').get_ancestors()

  assert set(ancestors.columns) == EXPECTED_COLUMNS

# SNOMED Tests
def test_read_relationship_file(spark_session):
  ancestors = with_relationships(
      spark_session,
      get_empty_hierarchies(spark_session),
      'tests/resources/SNOMED_RELATIONSHIP_SAMPLE.TXT',
      '20160901').get_ancestors()

  assert set(ancestors.columns) == EXPECTED_COLUMNS

# Bundles Tests
@fixture(scope="session")
def bundles(spark_session):
  return load_from_directory(spark_session, 'tests/resources/bundles', 1)

def test_load_from_directory(bundles):
  assert len(bundles.collect()) == 3

def test_extract_entry(spark_session, bundles):
  assert extract_entry(spark_session, bundles, 'Condition').count() == 5

def test_save_as_database(spark_session):
  spark_session.sql("CREATE DATABASE IF NOT EXISTS test_db")

  save_as_database(
      spark_session,
      'tests/resources/bundles',
      'test_db', 'Condition', 'Patient', 'Observation',
      minPartitions=1)

  assert spark_session.sql("SELECT * FROM test_db.condition").count() == 5
  assert spark_session.sql("SELECT * FROM test_db.patient").count() == 3
  assert spark_session.sql("SELECT * FROM test_db.observation").count() == 72

def test_to_bundle(spark_session, bundles):
  conditions = extract_entry(spark_session, bundles, 'Condition')

  assert to_bundle(spark_session, conditions) != None

# ValueSetsUdfs Tests
def test_isa_loinc(spark_session):
  with_loinc = with_loinc_hierarchy(
      spark_session,
      get_empty_hierarchies(spark_session),
      'tests/resources/LOINC_HIERARCHY_SAMPLE.CSV',
      '2.56')

  push_valuesets(spark_session,
                 {'leukocytes' : isa_loinc('LP14738-6')},
                 value_sets=get_empty_value_sets(spark_session),
                 hierarchies=with_loinc)
  
  expected = {'leukocytes' : [('http://loinc.org', '5821-4'),
                              ('http://loinc.org', 'LP14738-6'),
                              ('http://loinc.org', 'LP14419-3')]}
  assert get_current_valuesets(spark_session) == expected

def test_isa_snomed(spark_session):
  with_snomed = with_relationships(
      spark_session,
      get_empty_hierarchies(spark_session),
      'tests/resources/SNOMED_RELATIONSHIP_SAMPLE.TXT',
      '20160901')

  push_valuesets(spark_session,
                 {'diabetes' : isa_snomed('73211009')},
                 value_sets=get_empty_value_sets(spark_session),
                 hierarchies=with_snomed)

  expected = {'diabetes' : [('http://snomed.info/sct', '73211009'),
                            ('http://snomed.info/sct', '44054006')]}

  assert get_current_valuesets(spark_session) == expected

def test_isa_custom(spark_session, bundles):
  observations = extract_entry(spark_session, bundles, 'observation')
  observations.registerTempTable('observations')

  blood_pressure = {'blood_pressure' : [('http://loinc.org', '8462-4')]}

  value_sets = get_empty_value_sets(spark_session)
  hierarchies = get_empty_hierarchies(spark_session)

  push_valuesets(spark_session, blood_pressure, value_sets, hierarchies)
  
  results = spark_session.sql("SELECT subject.reference, "
      + "effectiveDateTime, "
      + "valueQuantity.value "
      + "FROM observations "
      + "WHERE in_valueset(code, 'blood_pressure')")

  assert get_current_valuesets(spark_session) == blood_pressure
  assert results.count() == 14
