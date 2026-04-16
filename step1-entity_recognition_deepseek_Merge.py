import os
import re
import time
import sys
import math
import json
from openai import OpenAI
from config_deepseek import API_TOKENS, INPUT_DIR, OUTPUT_DIR, PROMPT_DIR

# Ensure that the output directory exists
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# Define a unified prompt word file
PROMPT_FILE = "KOA_step1_实体抽取提示词.txt"

# API call parameters
API_DELAY = 0.5
MAX_RETRIES = 5
BASE_RETRY_DELAY = 1

# ============================== Command line parameter processing ==============================
if len(sys.argv) < 2:
    print("Please specify instance index (0 to total instances -1)")
    sys.exit(1)

try:
    INSTANCE_INDEX = int(sys.argv[1])
    TOTAL_INSTANCES = len(API_TOKENS)

    if INSTANCE_INDEX < 0 or INSTANCE_INDEX >= TOTAL_INSTANCES:
        print(f"Error: Instance index must be between 0 and {TOTAL_INSTANCES - 1}")
        sys.exit(1)

    print(f"Current instance index: {INSTANCE_INDEX}/{TOTAL_INSTANCES - 1}")
    print(f"The API key used for print (f) is: ...{API_TOKENS[INSTANCE_INDEX][-6:]}")

except Exception as e:
    print(f"Parameter error:{e}")
    sys.exit(1)

# ============================== Obtain and allocate patient folders ==============================
all_patient_dirs = sorted([
    d for d in os.listdir(INPUT_DIR)
    if os.path.isdir(os.path.join(INPUT_DIR, d))
])

total_patients = len(all_patient_dirs)
patients_per_instance = math.ceil(total_patients / TOTAL_INSTANCES)
start_index = INSTANCE_INDEX * patients_per_instance
end_index = min(start_index + patients_per_instance, total_patients)

print(f"Total number of patients: {total_patients} | This instance handles: {start_index}-{end_index - 1}")

# ============================== Read unified prompt words ==============================
prompt_path = os.path.join(PROMPT_DIR, PROMPT_FILE)
if not os.path.exists(prompt_path):
    print(f"Error: The prompt word file {prompt_path} does not exist")
    sys.exit(1)

with open(prompt_path, 'r', encoding='utf-8') as prompt_f:
    prompt = prompt_f.read().strip()

print(f"Unified prompt words loaded: {PROMPT_FILE}")


# ============================== Natural sorting function ==============================
def natural_sort_key(s):
    """
    Natural sorting key function, used to sort strings containing numbers
    """
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', s)]


# ============================== Logic of file processing sequence ==============================
def get_processing_order(files):
    """
    Determine the processing order based on the file list
    Return a list or group of files arranged in processing order
    """
    order = []

    # 1. Admission section
    admission_files = []

    #Priority search 入院_response.txt
    admission_main = [f for f in files if f == "入院_response.txt"]
    if admission_main:
        order.extend(admission_main)
    else:
        # Search for admission record files in descending order
        admission_patterns = [
            "入院记录-主诉_response.txt",
            "入院记录-现病史_response.txt",
            re.compile(r'^入院记录-中医(四诊|望诊)_response\.txt$'),
            "入院记录-专科检查_response.txt",
            re.compile(r'^入院记录-辅助检查(项目)?_response\.txt$')
        ]

        for pattern in admission_patterns:
            if isinstance(pattern, str):
                matched = [f for f in files if f == pattern]
            else:
                matched = [f for f in files if pattern.match(f)]

            if matched:
                admission_files.extend(matched)

        # If there are split admission documents, treat them as a group
        if admission_files:
            order.append(("admission", admission_files))

    # 2. First course/first course of illness section
    first_course_files = []

    #Priority search 首程_response.txt
    first_course_main = [f for f in files if f == "首程_response.txt"]
    if first_course_main:
        order.extend(first_course_main)
    else:
        # Search for the first medical record file in order of segmentation
        first_course_patterns = [
            "首次病程记录-病例特点_response.txt",
            re.compile(r'^首次病程记录-(首次病程-)?专科检查_response\.txt$'),
            re.compile(r'^首次病程记录-首次病程-西医诊断_response\.txt$'),
            re.compile(r'^首次病程记录-首次病程-中医诊断_response\.txt$'),
            "(合并)首程中西医诊断_response.txt",
            "首次病程记录-诊断依据_response.txt",
            "首次病程记录-诊疗计划_response.txt"
        ]

        for pattern in first_course_patterns:
            if isinstance(pattern, str):
                matched = [f for f in files if f == pattern]
            else:
                matched = [f for f in files if pattern.match(f)]

            if matched:
                first_course_files.extend(matched)

        # If there are split first leg files, treat them as a group
        if first_course_files:
            order.append(("first_course", first_course_files))

    # 3. Medical records section
    course_records = []

    # Search for all medical records files
    course_patterns = [
        re.compile(r'^\(拆分\)病程记录\d+_response\.txt$'),
        re.compile(r'^\(拆分\)日常病程记录\d+_response\.txt$'),
        re.compile(r'^日常病程记录\d+_response\.txt$'),
        "日常病程记录_response.txt",
        "病程记录_response.txt"
    ]

    for pattern in course_patterns:
        if isinstance(pattern, str):
            matched = [f for f in files if f == pattern]
        else:
            matched = [f for f in files if pattern.match(f)]

        if matched:
            course_records.extend(matched)

    # Sort the medical records by numbers
    course_records.sort(key=natural_sort_key)
    order.extend(course_records)

    # 4. Discharge section
    discharge_files = []

    #Priority search 出院_response.txt
    discharge_main = [f for f in files if f == "出院_response.txt"]
    if discharge_main:
        order.extend(discharge_main)
    else:
        # Search for discharge record files in descending order
        discharge_patterns = [
            "出院记录-入院情况_response.txt",
            "(合并)出院记录诊断_response.txt",
            "出院记录-诊疗经过_response.txt",
            "出院记录-出院情况_response.txt",
            "出院记录-出院医嘱_response.txt"
        ]

        for pattern in discharge_patterns:
            if isinstance(pattern, str):
                matched = [f for f in files if f == pattern]
            else:
                matched = [f for f in files if pattern.match(f)]

            if matched:
                discharge_files.extend(matched)

        # If there are split discharge documents, treat them as a group
        if discharge_files:
            order.append(("discharge", discharge_files))

    # 5. other parts
    other_files = []

    #Priority search 其他记录_response.txt
    other_main = [f for f in files if f == "其他记录_response.txt"]
    if other_main:
        order.extend(other_main)
    else:
        # Search for inspection and testing items
        other_patterns = [
            "检查项_response.txt",
            "检验项_response.txt"
        ]

        for pattern in other_patterns:
            matched = [f for f in files if f == pattern]
            if matched:
                other_files.extend(matched)

        order.extend(other_files)

    return order


# ============================== Record content of splicing and splitting ==============================
def combine_record_content(record_type, files, patient_path):
    """
    Splicing and splitting record content based on record type
    """
    content_parts = []

    # Define the mapping from files to titles
    title_map = {
        "入院": {
            "入院记录-主诉_response.txt": "主诉",
            "入院记录-现病史_response.txt": "现病史",
            "入院记录-中医四诊_response.txt": "中医四诊",
            "入院记录-中医望诊_response.txt": "中医望诊",
            "入院记录-专科检查_response.txt": "专科检查",
            "入院记录-辅助检查_response.txt": "辅助检查",
            "入院记录-辅助检查项目_response.txt": "辅助检查"
        },
        "首程": {
            "首次病程记录-病例特点_response.txt": "病例特点",
            "首次病程记录-专科检查_response.txt": "专科检查",
            "首次病程记录-首次病程-专科检查_response.txt": "专科检查",
            "首次病程记录-首次病程-西医诊断_response.txt": "西医诊断",
            "首次病程记录-首次病程-中医诊断_response.txt": "中医诊断",
            "(合并)首程中西医诊断_response.txt": "中西医诊断",
            "首次病程记录-诊断依据_response.txt": "诊断依据",
            "首次病程记录-诊疗计划_response.txt": "诊疗计划"
        },
        "出院": {
            "出院记录-入院情况_response.txt": "入院情况",
            "(合并)出院记录诊断_response.txt": "诊断",
            "出院记录-诊疗经过_response.txt": "诊疗经过",
            "出院记录-出院情况_response.txt": "出院情况",
            "出院记录-出院医嘱_response.txt": "出院医嘱"
        }
    }

    # Retrieve the title mapping of the current record type
    current_title_map = title_map.get(record_type, {})

    # Read and concatenate content in the order of the file list
    for filename in files:
        file_path = os.path.join(patient_path, filename)
        if not os.path.isfile(file_path):
            print(f"  Warning: {filename} is not a file, skip it")
            continue

        try:
            with open(file_path, 'r', encoding='utf-8') as record_file:
                file_content = record_file.read().strip()

            # Get the corresponding title
            title = current_title_map.get(filename, filename.replace('_response.txt', ''))

            # Add title and content
            content_parts.append(f"{title}：{file_content}")

        except Exception as e:
            print(f"    Failed to read file: {e}")
            continue

    # Connect all parts with line breaks
    return "\n".join(content_parts)


# ============================== Main processing loop ==============================
for idx in range(start_index, end_index):
    patient_dir_name = all_patient_dirs[idx]
    patient_path = os.path.join(INPUT_DIR, patient_dir_name)

    # Create corresponding output directory
    output_patient_dir = os.path.join(OUTPUT_DIR, patient_dir_name)
    if not os.path.exists(output_patient_dir):
        os.makedirs(output_patient_dir)

    # Output file path (one file per patient)
    output_file_path = os.path.join(output_patient_dir, f"{patient_dir_name}_step1.txt")

    # Check if it has been processed (skip if the file exists)
    if os.path.exists(output_file_path):
        print(f"✓ Patient {patient_dir_name} has been processed, skip")
        continue

    print(f"\nHandling patients {idx + 1}/{total_patients}: {patient_dir_name}")

    # Store a list of all entity rows
    all_entities = []

    # Retrieve all files from the patient folder
    all_files = os.listdir(patient_path)

    # Obtain processing sequence
    processing_order = get_processing_order(all_files)

    if not processing_order:
        print(f"⚠ Patient {patient_dir_name} did not find any files to process")
        continue

    print(f"  Processing sequence: {processing_order}")

    # Process files in the order they are processed
    for item in processing_order:
        # Processing individual files
        if isinstance(item, str):
            filename = item
            file_path = os.path.join(patient_path, filename)
            if not os.path.isfile(file_path):
                print(f"  Warning: {filename} is not a file, skip it")
                continue

            print(f"  Processing files: {filename}")

            # Read file content
            try:
                with open(file_path, 'r', encoding='utf-8') as record_file:
                    file_content = record_file.read()
                print(f"    File size: {len(file_content)} characters")
                content_to_process = file_content
            except Exception as e:
                print(f"    Failed to read file: {e}")
                continue

        # Processing file groups (split records)
        elif isinstance(item, tuple) and len(item) == 2:
            record_type, files = item
            print(f"  Processing{record_type}record group: {files}")

            # Record content of splicing and splitting
            content_to_process = combine_record_content(record_type, files, patient_path)
            print(f"    Size of spliced content: {len(content_to_process)} characters")

        else:
            print(f"  Unknown processing item: {item}")
            continue

        # Combine prompt words and file content
        content = prompt + "\n\n" + content_to_process
        message_content = ""

        # API call retry mechanism
        for attempt in range(MAX_RETRIES):
            try:
                print(f"    API call attempt {attempt + 1}/{MAX_RETRIES}")

                # Interacting with DeepSeek API using OpenAI SDK
                client = OpenAI(
                    api_key=API_TOKENS[INSTANCE_INDEX],
                    base_url="https://api.deepseek.com"
                )

                # Use streaming transmission
                response = client.chat.completions.create(
                    model="deepseek-reasoner",
                    messages=[{"role": "user", "content": content}],
                    stream=True,
                    max_tokens=32768,  #32K
                    temperature=0.0,
                    top_p=1.0,
                    frequency_penalty=0.0
                )

                # Collect streaming response content
                result = ""
                for chunk in response:
                    if chunk.choices[0].delta.content:
                        chunk_content = chunk.choices[0].delta.content
                        result += chunk_content

                message_content = result

                print(f"    API response successful, response length: {len(message_content)} character")
                break

            except Exception as e:
                print(
                    f"    {filename if isinstance(item, str) else record_type} An unexpected error occurred (attempting {attempt + 1}/{MAX_RETRIES}): {e}")
                import traceback

                traceback.print_exc()
                if attempt < MAX_RETRIES - 1:
                    wait_time = BASE_RETRY_DELAY * (2 ** attempt)
                    print(f"    Try again in{wait_time:.2f}seconds ..")
                    time.sleep(wait_time)
                else:
                    print(f"    {filename if isinstance(item, str) else record_type} Reached maximum retry count, skip this file")
                    message_content = ""
                    break

        # Process API responses and extract entity rows
        if message_content:
            # Extract entity rows from the response
            lines = message_content.strip().split('\n')
            extracted_count = 0
            for line in lines:
                line = line.strip()
                # Matched entity line format: Entity Type:Entity or Entity Type:Entity :: Context Anchor
                if line and (re.match(r'^[^:]+:.+$', line) or '::' in line):
                    all_entities.append(line)
                    extracted_count += 1
            print(
                f"    from {filename if isinstance(item, str) else record_type} extracted {extracted_count} entities，current total: {len(all_entities)} entities.")
        else:
            print(f"    {filename if isinstance(item, str) else record_type} No valid response received")

        # API call latency
        print(f"    Wait for {API_DELAY} seconds before making the next API call ..")
        time.sleep(API_DELAY)

    # Perform global deduplication on of entities before writing to files
    unique_entities = []
    seen_entities = set()
    for entity in all_entities:
        if entity not in seen_entities:
            unique_entities.append(entity)
            seen_entities.add(entity)

    # Write all entity lines to the output file
    if unique_entities:
        with open(output_file_path, 'w', encoding='utf-8') as output_file:
            for entity_line in unique_entities:
                output_file.write(entity_line + '\n')
        print(
            f"✓ Patient {patient_dir_name} processing completed, extracted {len(all_entities)} entities, deduplicated {len(unique_entities)} entities")
    else:
        print(f"⚠ Patient {patient_dir_name} did not extract any entities")

print("\nAll patients processed!")