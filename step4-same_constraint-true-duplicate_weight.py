import os
import csv
import re
from collections import defaultdict, Counter
from neo4j import GraphDatabase
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill

# ==================== Neo4j Connection Configuration ====================
uri = "bolt://localhost:7687"
username = ""
password = ""
driver = GraphDatabase.driver(uri, auth=(username, password))

# ==================== Global Configuration ====================
RELATIONS = [
    "中医辨病", "中医辨证", "中药内服治疗", "中药外用治疗", "其他中医特色疗法治疗",
    "分型", "对应中医病名", "建议检查", "得出结果", "手术治疗", "治法遣方",
    "组成药物", "西医诊断", "西医非药物疗法治疗", "西药关节腔注射治疗",
    "西药内用治疗", "西药外用治疗", "辨证取穴", "适用治法", "选穴",
    "针灸治疗", "药物功效", "疗法功效"
]
ATTRIBUTE_RELATIONS = {"药物功效", "疗法功效"}

triplet_frequency = Counter()
target_entities_effects = defaultdict(list)  # Storage target entity functionality (string)
TARGET_ENTITY_TYPES = ['中成药', '西药', '其他中医特色疗法', '西医非药物疗法']


# ==================== General tool functions ====================
def get_all_step3_files(root_folder):
    step3_files = []
    for root, dirs, files in os.walk(root_folder):
        for file in files:
            if file.endswith('_step3.txt'):
                step3_files.append(os.path.join(root, file))
    return step3_files


def parse_entity(entity_str):
    if ':' in entity_str:
        parts = entity_str.split(':', 1)
        return parts[0].strip(), parts[1].strip()
    else:
        if '，' in entity_str:
            entity_str = '、'.join(entity_str.split('，'))
        return "Entity", entity_str


def process_file(file_path):
    triplets = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and line.startswith('(') and line.endswith(')'):
                inner = line[1:-1]
                parts = [p.strip() for p in inner.split(', ')]
                if len(parts) == 3:
                    s_type, s_name = parse_entity(parts[0])
                    rel = parts[1]
                    o_type, o_name = parse_entity(parts[2])
                    triplets.append({
                        'subject_type': s_type, 'subject_name': s_name,
                        'relation': rel,
                        'object_type': o_type, 'object_name': o_name
                    })
    return triplets


def split_complex_effect(effect):
    # Support ',', ',', 'and' | 'separators
    parts = effect.split(' | ')
    result = []
    for part in parts:
        separators = ['，', '、', ',']
        pattern = '|'.join(map(re.escape, separators))
        subparts = re.split(pattern, part)
        for p in subparts:
            p_str = p.strip()
            # Filter out empty or literal '[]', '[]', 'none'
            if p_str and p_str not in ('[]', '[ ]', '无', '无明显'):
                result.append(p_str)
    return result


def merge_effects(existing_effects, new_effect):
    """
    Merge functions and return normalized function strings (stable sorting, deduplication, ignore order)
    Existing-effects: can be a string or a list of strings
    """
    # Compatible with strings and lists
    if isinstance(existing_effects, str):
        existing_effects = [existing_effects]
    all_parts = set()
    for eff in existing_effects:
        all_parts.update(split_complex_effect(eff))
    all_parts.update(split_complex_effect(new_effect))
    sorted_parts = sorted(all_parts)
    return " | ".join(sorted_parts) if sorted_parts else '-'


# ==================== Graph creation function ====================
def create_triplet_prescription_acupuncture(tx, subject_type, subject_name, relation, object_type, object_name,
                                            property_values=None,
                                            effect_value=None, object_name_effect=None):
    if relation in ["药物功效", "疗法功效"]:
        if property_values:
            if len(property_values) == 1:
                tx.run(
                    f"MERGE (a:{subject_type} {{name: $name, 功效: $value}})",
                    name=subject_name,
                    value=property_values[0]
                )
            else:
                formatted_values = "、".join([f"[{value}]" for value in property_values])
                tx.run(
                    f"MERGE (a:{subject_type} {{name: $name, 功效: $value}})",
                    name=subject_name,
                    value=formatted_values
                )
        else:
            tx.run(
                f"MERGE (a:{subject_type} {{name: $name, 功效: $value}})",
                name=subject_name,
                value=object_name
            )
    else:
        if subject_type in ["中药处方", "针灸疗法"] and effect_value:
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
            tx.run(
                f"MERGE (b:{object_type} {{name: $object_name}})",
                object_name=object_name
            )

        if subject_type in ["中药处方", "针灸疗法"] and effect_value:
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


def create_triplet_other_entities(tx, subject_type, subject_name, relation, object_type, object_name,
                                  property_values=None):
    if relation in ["药物功效", "疗法功效"]:
        if property_values:
            if len(property_values) == 1:
                tx.run(
                    f"MERGE (a:{subject_type} {{name: $name}}) SET a.功效 = $value",
                    name=subject_name,
                    value=property_values[0]
                )
            else:
                formatted_values = " | ".join(property_values)
                tx.run(
                    f"MERGE (a:{subject_type} {{name: $name}}) SET a.功效 = $value",
                    name=subject_name,
                    value=formatted_values
                )
        else:
            tx.run(
                f"MERGE (a:{subject_type} {{name: $name}}) SET a.功效 = $value",
                name=subject_name,
                value=object_name
            )
    else:
        tx.run(
            f"MERGE (a:{subject_type} {{name: $subject_name}})",
            subject_name=subject_name
        )
        tx.run(
            f"MERGE (b:{object_type} {{name: $object_name}})",
            object_name=object_name
        )
        tx.run(
            f"MATCH (a:{subject_type} {{name: $subject_name}}), "
            f"(b:{object_type} {{name: $object_name}}) "
            f"MERGE (a)-[r:{relation}]->(b)",
            subject_name=subject_name,
            object_name=object_name
        )


def process_single_file_triplets(file_path, session):
    print(f"Processing files: {file_path}")

    triplets = process_file(file_path)

    property_triplets = defaultdict(list)
    relation_triplets = []
    subject_name_set = set()
    prescription_effects = defaultdict(list)
    acupuncture_effects = defaultdict(list)
    properties_count = 0

    for triplet in triplets:
        if triplet['relation'] in ["药物功效", "疗法功效"]:
            properties_count += 1
            key = (triplet['subject_type'], triplet['subject_name'], triplet['relation'])
            if triplet['subject_type'] in TARGET_ENTITY_TYPES:
                entity_key = (triplet['subject_type'], triplet['subject_name'])
                current = target_entities_effects.get(entity_key)
                if current is None:
                    target_entities_effects[entity_key] = merge_effects([], triplet['object_name'])
                else:
                    target_entities_effects[entity_key] = merge_effects(current, triplet['object_name'])
            else:
                if triplet['subject_type'] == "中药处方":
                    prescription_effects[triplet['subject_name']].append(triplet['object_name'])
                elif triplet['subject_type'] == "针灸疗法":
                    acupuncture_effects[triplet['subject_name']].append(triplet['object_name'])
                else:
                    if triplet['object_name'] not in property_triplets[key]:
                        property_triplets[key].append(triplet['object_name'])
        else:
            relation_triplets.append(triplet)

        subject_name_set.add(triplet['subject_name'])

    # Efficacy of combination of traditional Chinese medicine prescription and acupuncture and moxibustion therapy
    for name in prescription_effects:
        merged = '-'
        for eff in prescription_effects[name]:
            if merged == '-':
                merged = merge_effects([], eff)
            else:
                merged = merge_effects(merged, eff)
        prescription_effects[name] = merged
    for name in acupuncture_effects:
        merged = '-'
        for eff in acupuncture_effects[name]:
            if merged == '-':
                merged = merge_effects([], eff)
            else:
                merged = merge_effects(merged, eff)
        acupuncture_effects[name] = merged

    # Set default values for ineffective Chinese medicine prescriptions and acupuncture and moxibustion therapy
    for subject_name in subject_name_set:
        if any(triplet['subject_type'] == "中药处方" and triplet['subject_name'] == subject_name for triplet in triplets):
            if subject_name not in prescription_effects:
                prescription_effects[subject_name] = '-'
        elif any(triplet['subject_type'] == "针灸疗法" and triplet['subject_name'] == subject_name for triplet in triplets):
            if subject_name not in acupuncture_effects:
                acupuncture_effects[subject_name] = '-'

    relations_count = len(relation_triplets)

    # First deal with the attribute triad of non target entities (including Chinese medicine prescriptions and acupuncture and moxibustion therapy)
    for (subject_type, subject_name, relation), values in property_triplets.items():
        if subject_type in ["中药处方", "针灸疗法"] and relation in ["药物功效", "疗法功效"]:
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
            if len(values) == 1:
                session.execute_write(
                    create_triplet_other_entities,
                    subject_type,
                    subject_name,
                    relation,
                    "Property",
                    values[0]
                )
            else:
                session.execute_write(
                    create_triplet_other_entities,
                    subject_type,
                    subject_name,
                    relation,
                    "Property",
                    None,
                    values
                )

    # Dealing with relationship triad, transmitting efficacy information for Chinese medicine prescriptions and acupuncture and moxibustion therapy
    for triplet in relation_triplets:
        effect_value = None
        if triplet['subject_type'] == "中药处方":
            effect_value = prescription_effects.get(triplet['subject_name'], '-')
        elif triplet['subject_type'] == "针灸疗法":
            effect_value = acupuncture_effects.get(triplet['subject_name'], '-')

        if triplet['subject_type'] in ["中药处方", "针灸疗法"]:
            session.execute_write(
                create_triplet_prescription_acupuncture,
                triplet['subject_type'],
                triplet['subject_name'],
                triplet['relation'],
                triplet['object_type'],
                triplet['object_name'],
                None,
                effect_value
            )
        elif triplet['object_type'] in ["中药处方", "针灸疗法"]:
            object_name_effect = None
            if triplet['object_type'] == "中药处方":
                object_name_effect = prescription_effects.get(triplet['object_name'], '-')
            else:
                object_name_effect = acupuncture_effects.get(triplet['object_name'], '-')
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

    print(f"Successfully processed {relations_count} relationships, {properties_count} attributes")
    return relations_count, properties_count


def process_target_entities_effects(session):
    print(f"Processing the efficacy attributes of four types of target entities, totaling {len(target_entities_effects)} entities")
    target_properties_count = 0
    for (entity_type, entity_name), effects in target_entities_effects.items():
        print(f"实体: {entity_type}:{entity_name}, 功效: {effects}")
        target_properties_count += 1
        session.execute_write(
            create_triplet_other_entities,
            entity_type,
            entity_name,
            "药物功效" if entity_type in ['中成药', '西药'] else "疗法功效",
            "Property",
            effects
        )
    return target_properties_count


def process_files_and_create_graph(root_folder):
    step3_files = get_all_step3_files(root_folder)
    if not step3_files:
        print(f"No _step3. txt file found in directory {root_folder} ")
        return
    print(f"Find {len(step3_files)} _step3. txt files")

    print("Phase 1: Process files and collect information ..")
    total_relations = 0
    total_properties = 0
    with driver.session() as session:
        for file_path in step3_files:
            relations_count, properties_count = process_single_file_triplets(file_path, session)
            total_relations += relations_count
            total_properties += properties_count

    print("Phase 2: Processing the efficacy attributes of four types of target entities ..")
    with driver.session() as session:
        target_properties_count = process_target_entities_effects(session)

    total_properties += target_properties_count
    print(f"processed a total of {total_relations} relationships and {total_properties} attributes")

    with driver.session() as session:
        print("\nTraditional Chinese Medicine Prescription Node Information:")
        result = session.run("MATCH (p:中药处方) RETURN p.name AS name, p.功效 AS effect")
        for record in result:
            print(f"中药处方: {record['name']}, 功效: {record['effect']}")
        print("\nNode information of acupuncture and moxibustion therapy:")
        result = session.run("MATCH (a:针灸疗法) RETURN a.name AS name, a.功效 AS effect")
        for record in result:
            print(f"针灸疗法: {record['name']}, 功效: {record['effect']}")
        print("\nFour types of target entity node information:")
        for entity_type in TARGET_ENTITY_TYPES:
            result = session.run(f"MATCH (p:{entity_type}) RETURN p.name AS name, p.功效 AS effect")
            for record in result:
                print(f"{entity_type}: {record['name']}, 功效: {record['effect']}")


def clear_database():
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    print("The database has been cleared")


# ==================== Weight statistics and import ====================
def count_triplets_for_weights(root_folder):
    global triplet_frequency
    triplet_frequency.clear()
    step3_files = get_all_step3_files(root_folder)
    print(f"Start counting the frequency of relationship triplets in {len(step3_files)} files ..")

    for file_path in step3_files:
        triplets = process_file(file_path)
        prescription_effects = defaultdict(list)
        acupuncture_effects = defaultdict(list)

        for t in triplets:
            if t['relation'] in ATTRIBUTE_RELATIONS:
                if t['subject_type'] == "中药处方":
                    prescription_effects[t['subject_name']].append(t['object_name'])
                elif t['subject_type'] == "针灸疗法":
                    acupuncture_effects[t['subject_name']].append(t['object_name'])

        for name in prescription_effects:
            all_parts = set()
            for eff in prescription_effects[name]:
                all_parts.update(split_complex_effect(eff))
            prescription_effects[name] = " | ".join(sorted(all_parts)) if all_parts else '-'
        for name in acupuncture_effects:
            all_parts = set()
            for eff in acupuncture_effects[name]:
                all_parts.update(split_complex_effect(eff))
            acupuncture_effects[name] = " | ".join(sorted(all_parts)) if all_parts else '-'

        all_prescription = {t['subject_name'] for t in triplets if t['subject_type'] == "中药处方"}
        for name in all_prescription:
            if name not in prescription_effects:
                prescription_effects[name] = '-'
        all_acupuncture = {t['subject_name'] for t in triplets if t['subject_type'] == "针灸疗法"}
        for name in all_acupuncture:
            if name not in acupuncture_effects:
                acupuncture_effects[name] = '-'

        for t in triplets:
            if t['relation'] in ATTRIBUTE_RELATIONS:
                continue
            s_type, s_name = t['subject_type'], t['subject_name']
            o_type, o_name = t['object_type'], t['object_name']

            if s_type == "中药处方":
                s_key = f"{s_name}|{prescription_effects[s_name]}"
            elif s_type == "针灸疗法":
                s_key = f"{s_name}|{acupuncture_effects[s_name]}"
            else:
                s_key = s_name

            if o_type == "中药处方":
                o_key = f"{o_name}|{prescription_effects[o_name]}"
            elif o_type == "针灸疗法":
                o_key = f"{o_name}|{acupuncture_effects[o_name]}"
            else:
                o_key = o_name

            key = (s_type, s_key, t['relation'], o_type, o_key)
            triplet_frequency[key] += 1

    print(f"Statistics completed, a total of {len(triplet_frequency)} different relationship triplets, with a total occurrence count {sum(triplet_frequency.values())}")


def format_entity_for_csv(entity_type, entity_key):
    if entity_type in ["中药处方", "针灸疗法"] and '|' in entity_key:
        name, effect = entity_key.split('|', 1)
        # If the efficacy is empty or '-', '[]', it will be uniformly displayed as [-]
        if effect in ('-', '', '[]', '[ ]'):
            return f"{entity_type}:{name}[-]"
        else:
            return f"{entity_type}:{name}[{effect}]"
    else:
        return f"{entity_type}:{entity_key}"


def save_frequency_to_csv(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    grouped = defaultdict(list)
    for (s_type, s_key, rel, o_type, o_key), cnt in triplet_frequency.items():
        if rel in ATTRIBUTE_RELATIONS:
            continue
        grouped[rel].append(((s_type, s_key, rel, o_type, o_key), cnt))

    for rel in RELATIONS:
        if rel in ATTRIBUTE_RELATIONS:
            continue
        data = grouped.get(rel, [])
        if not data:
            continue
        data.sort(key=lambda x: x[1], reverse=True)
        filename = f"{rel}.csv"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["triplet", "frequency"])
            for (s_type, s_key, rel, o_type, o_key), cnt in data:
                s_str = format_entity_for_csv(s_type, s_key)
                o_str = format_entity_for_csv(o_type, o_key)
                triplet_str = f"({s_str}, {rel}, {o_str})"
                writer.writerow([triplet_str, cnt])
        print(f" {len(data)} records have been written to {filename}")

    unknown = [((s_type, s_key, rel, o_type, o_key), cnt) for (s_type, s_key, rel, o_type, o_key), cnt in triplet_frequency.items()
               if rel not in RELATIONS and rel not in ATTRIBUTE_RELATIONS]
    if unknown:
        unknown.sort(key=lambda x: x[1], reverse=True)
        filepath = os.path.join(output_dir, "Unknown_relationship.csv")
        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["triple", "frequency"])
            for (s_type, s_key, rel, o_type, o_key), cnt in unknown:
                s_str = format_entity_for_csv(s_type, s_key)
                o_str = format_entity_for_csv(o_type, o_key)
                triplet_str = f"({s_str}, {rel}, {o_str})"
                writer.writerow([triplet_str, cnt])
        print(f" {len(unknown)} unknown relationship records have been written to unknown_relationship.csv")


def parse_triplet_string(triplet_str):
    s = triplet_str.strip()
    if s.startswith('(') and s.endswith(')'):
        s = s[1:-1]
    parts = [p.strip() for p in s.split(',')]
    if len(parts) != 3:
        return None
    subject_part = parts[0]
    rel = parts[1]
    object_part = parts[2]

    # Analyze the subject
    s_type, s_name, s_effect = None, None, None
    if ':' in subject_part:
        type_name = subject_part.split(':', 1)
        s_type = type_name[0].strip()
        rest = type_name[1].strip()
        if '[' in rest and rest.endswith(']'):
            name_part, effect_part = rest.split('[', 1)
            s_name = name_part.strip()
            s_effect = effect_part[:-1].strip()
            # New: Consider literal '[]' as ineffective '-'
            if s_effect in ('', '-', '[]', '[ ]', 'None'):
                s_effect = '-'
        else:
            s_name = rest
            s_effect = '-'
    else:
        s_type = "Entity"
        s_name = subject_part
        s_effect = '-'

    # Analyze the object
    o_type, o_name, o_effect = None, None, None
    if ':' in object_part:
        type_name = object_part.split(':', 1)
        o_type = type_name[0].strip()
        rest = type_name[1].strip()
        if '[' in rest and rest.endswith(']'):
            name_part, effect_part = rest.split('[', 1)
            o_name = name_part.strip()
            o_effect = effect_part[:-1].strip()
            # New: Consider literal '[]' as ineffective '-'
            if o_effect in ('', '-', '[]', '[ ]', 'None'):
                o_effect = '-'
        else:
            o_name = rest
            o_effect = '-'
    else:
        o_type = "Entity"
        o_name = object_part
        o_effect = '-'

    # For entities that are not prescribed by traditional Chinese medicine/acupuncture and moxibustion therapy, the efficacy should be None (no matching efficacy is required in the weight dictionary)
    if s_type not in ["中药处方", "针灸疗法"]:
        s_effect = None
    if o_type not in ["中药处方", "针灸疗法"]:
        o_effect = None

    return s_type, s_name, s_effect, rel, o_type, o_name, o_effect


def load_weights_from_csv(csv_folder):
    relation_weights = {}
    for rel in RELATIONS:
        if rel in ATTRIBUTE_RELATIONS:
            continue
        csv_file = os.path.join(csv_folder, f"{rel}.csv")
        if not os.path.exists(csv_file):
            continue
        with open(csv_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if len(row) < 2:
                    continue
                triplet_str, freq_str = row[0], row[1]
                try:
                    freq = int(freq_str)
                except:
                    continue
                parsed = parse_triplet_string(triplet_str)
                if parsed is None:
                    continue
                s_type, s_name, s_effect, rel, o_type, o_name, o_effect = parsed
                # Ensure that the parsing value is used when the efficacy is not None, otherwise it will be ignored during matching
                key = (s_type, s_name, s_effect, rel, o_type, o_name, o_effect)
                relation_weights[key] = freq
    return relation_weights


def update_relation_weights_in_neo4j(relation_weights):
    """Set weight attribute for matching relationships in Neo4j (supports functional differentiation)"""
    if not relation_weights:
        print("No weight data, skip update")
        return

    success = 0
    fail = 0
    with driver.session() as session:
        for (s_type, s_name, s_effect, rel, o_type, o_name, o_effect), weight in relation_weights.items():
            # Construct subject matching conditions
            if s_type in ["中药处方", "针灸疗法"] and s_effect is not None:
                s_match = f"(a:{s_type} {{name: $s_name, 功效: $s_effect}})"
            else:
                s_match = f"(a:{s_type} {{name: $s_name}})"
            # Construct object matching conditions
            if o_type in ["中药处方", "针灸疗法"] and o_effect is not None:
                o_match = f"(b:{o_type} {{name: $o_name, 功效: $o_effect}})"
            else:
                o_match = f"(b:{o_type} {{name: $o_name}})"

            cypher = f"""
            MATCH {s_match}
            MATCH {o_match}
            MATCH (a)-[r:{rel}]->(b)
            SET r.weight = $weight
            RETURN r
            """
            params = {
                "s_name": s_name,
                "o_name": o_name,
                "weight": weight
            }
            if s_type in ["中药处方", "针灸疗法"] and s_effect is not None:
                params["s_effect"] = s_effect
            if o_type in ["中药处方", "针灸疗法"] and o_effect is not None:
                params["o_effect"] = o_effect
            try:
                result = session.run(cypher, params)
                if result.peek() is None:
                    print(f"Warning: No relationship found {s_type}:{s_name}[{s_effect}] -{rel}-> {o_type}:{o_name}[{o_effect}]")
                    fail += 1
                else:
                    success += 1
            except Exception as e:
                print(f"Execution failed: {s_type}:{s_name}[{s_effect}] -{rel}-> {o_type}:{o_name}[{o_effect}], Error: {e}")
                fail += 1
    print(f"Successfully updated {success} relationships, failed/unmatched {fail} relationships")


# ==================== 主函数 ====================
def main():
    root_folder = "./output-triplet_deepseek"
    csv_output_dir = "./statistical_result_(triplet)"

    if not os.path.exists(csv_output_dir) or not os.listdir(csv_output_dir):
        print("Step 1: Count the frequency of relationship triplets and generate a classification CSV")
        count_triplets_for_weights(root_folder)
        save_frequency_to_csv(csv_output_dir)
        print("CSV file generation completed")
    else:
        print("Step 1: CSV file already exists, skip the statistics step")

    print("Step 2: Load weights from CSV file ..")
    relation_weights = load_weights_from_csv(csv_output_dir)
    print(f"loaded {len(relation_weights)} weight records")

    print("Step 3: Create a Neo4j graph ..")
    target_entities_effects.clear()
    process_files_and_create_graph(root_folder)

    print("Step 4: Update the relationship weight attributes ..")
    update_relation_weights_in_neo4j(relation_weights)

    driver.close()
    print("All done!")


if __name__ == "__main__":
    main()