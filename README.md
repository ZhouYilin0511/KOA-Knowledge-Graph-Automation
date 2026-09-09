# KOA-Knowledge-Graph-Automation

## Project Overview
This repository provides the accompanying code and prompt resources for the paper titled "Automated Knowledge Extraction from Chinese Electronic Medical Records and the Construction of a Traditional Chinese Medicine and Western Medicine Integrated Knowledge Graph for Knee Osteoarthritis (KOA)." The study utilizes the DeepSeek-V4-Pro large language model and a stepwise fine-tuned prompt engineering approach to automatically extract medical entities, relations, and attributes from multi-center Chinese electronic medical records (EMRs). After knowledge fusion, a knowledge graph for KOA combining both Traditional Chinese Medicine (TCM) and Western Medicine is constructed, with support for import into Neo4j for graph database storage and visualization.

The repository includes code for automated knowledge extraction, knowledge fusion, and Neo4j import, along with corresponding prompt templates. Due to privacy protection, data security, and ethical requirements, the repository does not provide raw clinical data containing personal identifying information; instead, it includes one strictly anonymized sample clinical record from each participating hospital across multiple centers to illustrate the data format and content.

## Repository Structure
```
.
├── config_deepseek.py                              # DeepSeek API configuration file
├── step1_entity_recognition_deepseek_Merge.py      # Entity extraction (merged results)
├── step2_relationship_link_deepseek.py             # Relation and attribute extraction
├── step3_knowledge_fusion.py                       # Knowledge fusion
├── step4_same_constraint_true_duplicate.py         # Synonym constraints and deduplication
├── step4_same_constraint_true_duplicate_weight.py  # Weighted deduplication and fusion
├── prompts/
│   ├── KOA_Step1_Entity_Extraction_Prompt.txt      # Entity extraction prompts (English)
│   ├── KOA_step1_实体抽取提示词.txt                 # Entity extraction prompts (Chinese)
│   ├── KOA_Step2_Relation_Extraction_Prompt.txt    # Relation extraction prompts (English)
│   ├── KOA_step2_关系抽取提示词.txt                # Relation extraction prompts (Chinese)
│   ├── KOA_Step3_Knowledge_Fusion_Prompt.txt       # Knowledge fusion prompts (English)
│   └── KOA_step3_知识融合提示词.txt                # Knowledge fusion prompts (Chinese)
├── sample_records/                                 # Multi-center anonymized sample clinical records
│   ├── hutcm1st/                                   # Sample from HUTCM 1st
│   ├── hutcm2nd/                                   # Sample from HUTCM 2nd
│   └── cstcm/                                      # Sample from CSTCM
└── README.md
```

## Methodology
The automated knowledge extraction and graph construction process in this study includes the following four key steps:

1.Entity Extraction (Step1): Using DeepSeek-V4-Pro and the defined prompts, identify 17 types of medical entities (e.g., symptoms, signs, TCM syndromes, Chinese herbal prescriptions, etc.) from unstructured EMRs, and output the list of extracted entities.

2.Relation and Attribute Extraction (Step2): Identify 21 types of semantic relationships between entities (such as Western medicine diagnosis, TCM differentiation, and treatment relations), and extract the efficacy attributes of drugs and therapies to output the relation and attribute triples.

3.Knowledge Fusion (Step3): Standardize and merge synonymous entities, similar expressions, and non-standard nomenclature, producing consistent and redundant-free structured knowledge.

4.Graph Import (Step4): Import the structured knowledge into Neo4j for storage, querying, and visualization.

## Key Experimental Results
The methodology was evaluated on 50 randomly selected full-cycle EMRs from 1,884 KOA inpatient patients (covering admission, clinical course, and discharge records, totaling 777 text files). Under zero-shot conditions, the following core performance metrics were achieved with DeepSeek-V4-Pro:
|Task	                  |Precision (mean±std) 	|Recall (mean±std)	 |F1 (mean±std)
|---|---|---|---|
|Entity extraction	    |0.9106±0.0030	        |0.8915±0.0058	     |0.9009±0.0035
|Relation extraction	  |0.9829±0.0035	        |0.9200±0.0302	     |0.9501±0.0147
|Attribute extraction 	|0.9474±0.0061	        |0.9151±0.0384	     |0.9306±0.0185

Detailed evaluation results can be found in the paper.

## Usage Instructions
### Environment Requirements
Python 3.8+

Dependencies: openai (or compatible DeepSeek API client), pandas, py2neo (for Neo4j integration).

## API Configuration
Set the DeepSeek API key in the code.

## Input Data
Prepare the EMR text files to be extracted (for format examples, see the methods section of the paper). This repository does not provide raw clinical data.

## Execution Order
Execute the following steps in sequence:

1.step1_entity_recognition_deepseek_Merge.py - Entity extraction

2.step2_relationship_link_deepseek.py - Relation and attribute extraction

3.step3_knowledge_fusion.py - Knowledge fusion

4.Optionally, execute step4_same_constraint_true_duplicate.py (standard deduplication) or step4_same_constraint_true_duplicate_weight.py (weighted deduplication) based on your needs.
Customization of Prompts
You may modify the corresponding prompt files in the prompts/ directory for different entity types or relationship definitions as required.

## Prompt Files
The prompts/ directory contains both English and Chinese versions of the prompt files for the corresponding tasks:

KOA_Step1_Entity_Extraction_Prompt.txt / KOA_step1_实体抽取提示词.txt: Prompts for entity extraction, defining entity types and output formats.

KOA_Step2_Relation_Extraction_Prompt.txt / KOA_step2_关系抽取提示词.txt: Prompts for relation and attribute extraction, defining relationship types and attribute extraction requirements.

KOA_Step3_Knowledge_Fusion_Prompt.txt / KOA_step3_知识融合提示词.txt: Prompts for knowledge fusion, used for merging synonymous entities and standardization.

## Important Notes
This code and prompts are for academic research purposes only and do not include any identifiable patient data.

Please adhere to the terms of service when using the DeepSeek API.

If you use this resource in your work, please cite the related paper.
