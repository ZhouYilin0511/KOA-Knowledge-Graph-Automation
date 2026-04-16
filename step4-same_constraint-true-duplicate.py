import os
from neo4j import GraphDatabase
from collections import defaultdict
import re

# Connect to Neo4j database
uri = "bolt://localhost:7687"
username = ""
password = ""
driver = GraphDatabase.driver(uri, auth=(username, password))


# Recursive search for all step3.txt files
def get_all_step3_files(root_folder):
    step3_files = []
    for root, dirs, files in os.walk(root_folder):
        for file in files:
            if file.endswith('_step3.txt'):
                full_path = os.path.join(root, file)
                step3_files.append(full_path)
    return step3_files


# Parse triplets in files
def process_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.readlines()
        triplets = []
        for line in content:
            line = line.strip()
            if line and line.startswith('(') and line.endswith(')'):
                line_content = line[1:-1]
                parts = [part.strip() for part in line_content.split(', ')]   # Split symbols in triplets
                if len(parts) == 3:
                    subject_type, subject_name = parse_entity(parts[0])
                    relation = parts[1]
                    object_type, object_name = parse_entity(parts[2])

                    triplets.append({
                        'subject_type': subject_type,
                        'subject_name': subject_name,
                        'relation': relation,
                        'object_type': object_type,
                        'object_name': object_name
                    })
                else:
                    print(f"Unresolvable line: {line}, the number of split parts is not 3")
            elif line:
                print(f"Line with incorrect format: {line}")
        return triplets


# Resolve entity types and names
def parse_entity(entity_str):
    if ':' in entity_str:
        parts = entity_str.split(':', 1)
        entity_type = parts[0].strip()
        entity_name = parts[1].strip()
        return entity_type, entity_name
    else:
        if '，' in entity_str:
            entity_str = '、'.join(entity_str.split('，'))
        return "Entity", entity_str


# The function of splitting punctuation marks
def split_complex_effect(effect):
    """
    Split efficacy strings containing punctuation
    For example: "Relieve local adhesive joints, unblock meridians and collaterals, unblock collaterals and relieve pain" ->["Relieve local adhesive joints", "unblock meridians and collaterals", "unblock collaterals and relieve pain"]
    """
    # Define separators: Chinese comma, Chinese comma, English comma
    separators = ['，', '、', ',']

    # First, use regular expressions to match all separators for splitting
    pattern = '|'.join(map(re.escape, separators))
    parts = re.split(pattern, effect)

    # Remove whitespace and filter empty strings
    parts = [part.strip() for part in parts if part.strip()]

    return parts


# Check if the efficacy is included
def is_effect_contained(effect, target_effect):
    """
    Check if a single efficacy is included in the target efficacy
    For example, "pain relief" is included in "meridian pain relief
    """
    return effect in target_effect and effect != target_effect


# Merge functions to avoid duplication
def merge_effects(existing_effects, new_effect):
    """
    Merge efficacy, return the merged efficacy list
    New strategy: Split all efficacy into the smallest unit, then deduplicate and finally recombine
    """
    # Split all existing functions into the smallest unit
    all_effect_parts = set()

    # Dealing with existing efficacy
    for effect in existing_effects:
        parts = split_complex_effect(effect)
        all_effect_parts.update(parts)

    # Dealing with new effects
    new_parts = split_complex_effect(new_effect)
    all_effect_parts.update(new_parts)

    # De duplication: removing parts that are included in other functions
    final_effects = set()
    sorted_effects = sorted(all_effect_parts, key=len, reverse=True)  # First deal with the long ones

    for effect in sorted_effects:
        # Check if the current efficacy is included in the selected efficacy
        is_contained = any(
            effect != selected and effect in selected
            for selected in final_effects
        )

        if not is_contained:
            # Check if the current efficacy includes the selected efficacy
            to_remove = []
            for selected in final_effects:
                if selected != effect and selected in effect:
                    to_remove.append(selected)

            # Remove shorter effects included in the current effect
            for item in to_remove:
                final_effects.remove(item)

            # Add current efficacy
            final_effects.add(effect)

    # Combine the final effect into a string list
    result = list(final_effects)

    return result


# Create nodes and relationships for Chinese medicine prescriptions and acupuncture and moxibustion therapy in Neo4j
def create_triplet_prescription_acupuncture(tx, subject_type, subject_name, relation, object_type, object_name,
                                            property_values=None,
                                            effect_value=None, object_name_effect=None):
    # Check if it is an attribute triplet
    if relation in ["药物功效", "疗法功效"]:
        # Attribute triplet: Add attributes to nodes
        if property_values:
            # If there are multiple values, store them in the specified format
            if len(property_values) == 1:
                # Only one value, stored directly as a string
                tx.run(
                    f"MERGE (a:{subject_type} {{name: $name, 功效: $value}})",
                    name=subject_name,
                    value=property_values[0]
                )
            else:
                # There are multiple values stored in the format of [value1] and [value2]
                formatted_values = "、".join([f"[{value}]" for value in property_values])
                tx.run(
                    f"MERGE (a:{subject_type} {{name: $name, 功效: $value}})",
                    name=subject_name,
                    value=formatted_values
                )
        else:
            # The situation of a single attribute value
            tx.run(
                f"MERGE (a:{subject_type} {{name: $name, 功效: $value}})",
                name=subject_name,
                value=object_name
            )
    else:
        # Relationship triplet: Create two nodes and their relationships
        # For traditional Chinese medicine prescriptions and acupuncture and moxibustion therapy nodes, if there is efficacy information, it contains efficacy attributes
        if subject_type in ["中药处方", "针灸疗法"] and effect_value:
            # Using both name and efficacy as unique identifiers
            tx.run(
                f"MERGE (a:{subject_type} {{name: $subject_name, 功效: $effect}})",
                subject_name=subject_name,
                effect=effect_value
            )
        else:
            tx.run(
                f"MERGE (a:{subject_type} {{name: $subject_name}})",
                subject_name=subject_name
            )

        if object_name_effect:
            tx.run(
                f"MERGE (b:{object_type} {{name: $object_name, 功效: $effect}})",
                object_name=object_name,
                effect=object_name_effect
            )
        else:
            # Create object nodes
            tx.run(
                f"MERGE (b:{object_type} {{name: $object_name}})",
                object_name=object_name
            )

        # Create a relationship
        if subject_type in ["中药处方", "针灸疗法"] and effect_value:
            # For effective nodes, use efficacy to match nodes
            tx.run(
                f"MATCH (a:{subject_type} {{name: $subject_name, 功效: $effect}}), "
                f"(b:{object_type} {{name: $object_name}}) "
                f"MERGE (a)-[r:{relation}]->(b)",
                subject_name=subject_name,
                effect=effect_value,
                object_name=object_name
            )
        else:
            if object_name_effect:
                tx.run(
                    f"MATCH (a:{subject_type} {{name: $subject_name}}), "
                    f"(b:{object_type} {{name: $object_name, 功效: $effect}}) "
                    f"MERGE (a)-[r:{relation}]->(b)",
                    subject_name=subject_name,
                    object_name=object_name,
                    effect=object_name_effect,
                )
            else:
                tx.run(
                    f"MATCH (a:{subject_type} {{name: $subject_name}}), "
                    f"(b:{object_type} {{name: $object_name}}) "
                    f"MERGE (a)-[r:{relation}]->(b)",
                    subject_name=subject_name,
                    object_name=object_name
                )


# Create nodes and relationships for the other four types of entities in Neo4j
def create_triplet_other_entities(tx, subject_type, subject_name, relation, object_type, object_name,
                                  property_values=None):
    # Check if it is an attribute triplet
    if relation in ["药物功效", "疗法功效"]:
        # Attribute triplet: Add attributes to nodes
        if property_values:
            # If there are multiple values, store them in the specified format
            if len(property_values) == 1:
                # Only one value, stored directly as a string
                tx.run(
                    f"MERGE (a:{subject_type} {{name: $name}}) SET a.功效 = $value",
                    name=subject_name,
                    value=property_values[0]
                )
            else:
                # There are multiple values stored in the format of [value1] and [value2]
                formatted_values = " | ".join(property_values)
                tx.run(
                    f"MERGE (a:{subject_type} {{name: $name}}) SET a.功效 = $value",
                    name=subject_name,
                    value=formatted_values
                )
        else:
            # The situation of a single attribute value
            tx.run(
                f"MERGE (a:{subject_type} {{name: $name}}) SET a.功效 = $value",
                name=subject_name,
                value=object_name
            )
    else:
        # Relationship triplet: Create two nodes and their relationships
        tx.run(
            f"MERGE (a:{subject_type} {{name: $subject_name}})",
            subject_name=subject_name
        )

        # Create object nodes
        tx.run(
            f"MERGE (b:{object_type} {{name: $object_name}})",
            object_name=object_name
        )

        # Create a relationship
        tx.run(
            f"MATCH (a:{subject_type} {{name: $subject_name}}), "
            f"(b:{object_type} {{name: $object_name}}) "
            f"MERGE (a)-[r:{relation}]->(b)",
            subject_name=subject_name,
            object_name=object_name
        )


# Global storage of functional information for four types of entities
target_entities_effects = defaultdict(list)
# Define four types of entities that require special handling
TARGET_ENTITY_TYPES = ['中成药', '西药', '其他中医特色疗法', '西医非药物疗法']


# Process all triplets in a single file and merge attributes of the same entity
def process_single_file_triplets(file_path, session):
    print(f"处理文件: {file_path}")

    # Parse triplets in files
    triplets = process_file(file_path)

    # Dictionary for storing attribute triplets
    property_triplets = defaultdict(list)
    relation_triplets = []
    subject_name_set = set()  # Count all entity names
    prescription_effects = defaultdict(list)
    acupuncture_effects = defaultdict(list)

    # Add attribute counter
    properties_count = 0

    # Separate attribute triplets and relationship triplets
    for triplet in triplets:
        if triplet['relation'] in ["药物功效", "疗法功效"]:
            # Each attribute triplet counts
            properties_count += 1

            key = (triplet['subject_type'], triplet['subject_name'], triplet['relation'])

            # For the four types of target entities, first collect them into the global dictionary
            if triplet['subject_type'] in TARGET_ENTITY_TYPES:
                entity_key = (triplet['subject_type'], triplet['subject_name'])
                # Merge functions to avoid duplication
                target_entities_effects[entity_key] = merge_effects(
                    target_entities_effects[entity_key],
                    triplet['object_name']
                )
            else:
                # Record prescriptions and their efficacy
                if triplet['subject_type'] == "中药处方":
                    prescription_effects[triplet['subject_name']].append(triplet['object_name'])
                # Record acupuncture and moxibustion therapy and efficacy
                elif triplet['subject_type'] == "针灸疗法":
                    acupuncture_effects[triplet['subject_name']].append(triplet['object_name'])
                else:
                    if triplet['object_name'] not in property_triplets[key]:
                        property_triplets[key].append(triplet['object_name'])
        else:
            relation_triplets.append(triplet)

        subject_name_set.add(triplet['subject_name'])

    # Set default values for ineffective Chinese medicine prescriptions and acupuncture and moxibustion therapy
    for subject_name in subject_name_set:
        # Check if it is a traditional Chinese medicine prescription without efficacy records
        if any(triplet['subject_type'] == "中药处方" and triplet['subject_name'] == subject_name for triplet in
               triplets):
            if subject_name not in prescription_effects:
                prescription_effects[subject_name] = ['-']
        # Check whether it is acupuncture and moxibustion therapy, but there is no efficacy record
        elif any(triplet['subject_type'] == "针灸疗法" and triplet['subject_name'] == subject_name for triplet in
                 triplets):
            if subject_name not in acupuncture_effects:
                acupuncture_effects[subject_name] = ['-']

    # Count the number of relationships
    relations_count = len(relation_triplets)

    # First deal with the attribute triad of non target entities (including Chinese medicine prescriptions and acupuncture and moxibustion therapy)
    for (subject_type, subject_name, relation), values in property_triplets.items():
        # For the efficacy of traditional Chinese medicine prescription and acupuncture and moxibustion therapy, the name and efficacy are used as the only identification
        if subject_type in ["中药处方", "针灸疗法"] and relation in ["药物功效", "疗法功效"]:
            # Create separate nodes for each efficacy value
            for effect_value in values:
                if subject_type == "中药处方" and subject_name in prescription_effects:
                    session.execute_write(
                        create_triplet_prescription_acupuncture,
                        subject_type,
                        subject_name,
                        relation,
                        "Property",
                        effect_value
                    )
                elif subject_type == "针灸疗法" and subject_name in acupuncture_effects:
                    session.execute_write(
                        create_triplet_prescription_acupuncture,
                        subject_type,
                        subject_name,
                        relation,
                        "Property",
                        effect_value
                    )
        else:
            # Process other attributes as they are
            if len(values) == 1:
                # Only one value, passed directly
                session.execute_write(
                    create_triplet_other_entities,
                    subject_type,
                    subject_name,
                    relation,
                    "Property",
                    values[0]
                )
            else:
                # There are multiple values, pass the entire list
                session.execute_write(
                    create_triplet_other_entities,
                    subject_type,
                    subject_name,
                    relation,
                    "Property",
                    None,  # object_name 设为 None
                    Values # Passing a list of attribute values
                )

    # Then deal with the relationship triad to deliver efficacy information for Chinese medicine prescriptions and acupuncture and moxibustion therapy
    for triplet in relation_triplets:
        # Obtain the efficacy of Chinese medicine prescriptions and acupuncture and moxibustion therapy (if any)
        effect_value = None
        if triplet['subject_type'] == "中药处方":
            # Search for all efficacy related to this prescription
            if triplet['subject_name'] in prescription_effects:
                effect_value = get_effect_value(prescription_effects, triplet['subject_name'])
            else:
                effect_value = '-'
        elif triplet['subject_type'] == "针灸疗法":
            # Find all the effects related to this acupuncture and moxibustion therapy
            if triplet['subject_name'] in acupuncture_effects:
                effect_value = get_effect_value(acupuncture_effects, triplet['subject_name'])
            else:
                effect_value = '-'

        # Select different creation functions based on entity types
        if triplet['subject_type'] in ["中药处方", "针灸疗法"]:
            session.execute_write(
                create_triplet_prescription_acupuncture,
                triplet['subject_type'],
                triplet['subject_name'],
                triplet['relation'],
                triplet['object_type'],
                triplet['object_name'],
                None,  # property_values
                effect_value  # Transfer efficacy information (only effective for Chinese medicine prescriptions and acupuncture and moxibustion therapy)
            )
        elif triplet['object_type'] in ["中药处方", "针灸疗法"]:
            object_name_effect = None
            if triplet['object_name'] in prescription_effects:
                object_name_effect = get_effect_value(prescription_effects, triplet['object_name'])
            elif triplet['object_name'] in acupuncture_effects:
                object_name_effect = get_effect_value(acupuncture_effects, triplet['object_name'])
            else:
                object_name_effect = '-'
            session.execute_write(
                create_triplet_prescription_acupuncture,
                triplet['subject_type'],
                triplet['subject_name'],
                triplet['relation'],
                triplet['object_type'],
                triplet['object_name'],
                object_name_effect=object_name_effect
            )
        else:
            session.execute_write(
                create_triplet_other_entities,
                triplet['subject_type'],
                triplet['subject_name'],
                triplet['relation'],
                triplet['object_type'],
                triplet['object_name']
            )

    print(f"Successfully processed {relations_count} relationships，{properties_count} attributes")
    return relations_count, properties_count


def get_effect_value(effect_dict: dict, name: str) -> str:
    if len(effect_dict[name]) > 1:
        effect_value = ' | '.join(effect_dict[name])
    else:
        effect_value = effect_dict[name][0]
    return effect_value


# Handling the efficacy attributes of four types of target entities
def process_target_entities_effects(session):
    print(f"Processing the efficacy attributes of four types of target entities, totaling {len(target_entities_effects)} entities")

    # Count the number of attributes processed in the second stage
    target_properties_count = 0

    for (entity_type, entity_name), effects in target_entities_effects.items():
        print(f"Entity: {entity_type}:{entity_name}, Effect: {effects}")
        target_properties_count += len(effects)  # Each efficacy value counts as an attribute

        if len(effects) == 1:
            session.execute_write(
                create_triplet_other_entities,
                entity_type,
                entity_name,
                "药物功效" if entity_type in ['中成药', '西药'] else "疗法功效",
                "Property",
                effects[0]
            )
        else:
            session.execute_write(
                create_triplet_other_entities,
                entity_type,
                entity_name,
                "药物功效" if entity_type in ['中成药', '西药'] else "疗法功效",
                "Property",
                None,  # object_name 设为 None
                effects  # Transfer attribute value list
            )

    return target_properties_count


# Batch processing files to generate graphs
def process_files_and_create_graph(root_folder):
    # Retrieve all step3.txt files
    step3_files = get_all_step3_files(root_folder)

    if not step3_files:
        print(f"No _step3. txt file found in directory {root_folder}")
        return

    print(f"Find {len(step3_files)} _step3. txt files")

    # Phase 1: Process all files and collect information
    print("Phase 1: Process files and collect information ..")
    total_relations = 0
    total_properties = 0
    with driver.session() as session:
        for file_path in step3_files:
            # Create independent transactions for each file
            relations_count, properties_count = process_single_file_triplets(file_path, session)
            total_relations += relations_count
            total_properties += properties_count

    # Phase 2: Processing the efficacy attributes of four types of target entities
    print("Phase 2: Processing the efficacy attributes of four types of target entities ..")
    with driver.session() as session:
        target_properties_count = process_target_entities_effects(session)

    print(f"processed a total of {total_relations} relationships and {total_properties} attributes")

    # Print all six types of entity node information
    print("\nTraditional Chinese Medicine Prescription Node Information:")
    with driver.session() as session:
        result = session.run("MATCH (p:中药处方) RETURN p.name AS name, p.功效 AS effect")
        for record in result:
            print(f"中药处方: {record['name']}, 功效: {record['effect']}")

    # Print acupuncture and moxibustion Therapy Node Information
    print("\nNode information of acupuncture and moxibustion therapy:")
    with driver.session() as session:
        result = session.run("MATCH (a:针灸疗法) RETURN a.name AS name, a.功效 AS effect")
        for record in result:
            print(f"针灸疗法: {record['name']}, 功效: {record['effect']}")

    print("\nFour types of target entity node information:")
    with driver.session() as session:
        for entity_type in TARGET_ENTITY_TYPES:
            result = session.run(f"MATCH (p:{entity_type}) RETURN p.name AS name, p.功效 AS effect")
            for record in result:
                print(f"{entity_type}: {record['name']}, 功效: {record['effect']}")


# Clean up the database (optional, for re importing)
def clear_database():
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    print("The database has been cleared")


# Main function
def main():
    root_folder = "output-triplet_deepseek"  # Your root directory

    # Optional: Clear the database and import again
    # clear_database()

    # Clear global storage to ensure that each run starts over (this ensures that the efficacy information of the four types of entities is collected from scratch every time the program runs)
    target_entities_effects.clear()

    process_files_and_create_graph(root_folder)

    # Close database connection
    driver.close()


if __name__ == "__main__":
    main()