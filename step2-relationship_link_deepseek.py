import os
import re
import time
import sys
import math
from config_deepseek import API_TOKENS, INPUT_DIR, OUTPUT_DIR, PROMPT_DIR
from openai import OpenAI

# Ensure that the output directory exists
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# Define a unified prompt word file
PROMPT_FILE = "KOA_step2_关系抽取提示词.txt"

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
        print(f"Error:Instance index must be between 0 and{TOTAL_INSTANCES - 1}")
        sys.exit(1)

    print(f"Current instance index:{INSTANCE_INDEX}/{TOTAL_INSTANCES - 1}")
    print(f"API key used: ..{API_TOKENS[INSTANCE_INDEX][-6:]}")

except Exception as e:
    print(f"Parameter error: {e}")
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

print(f"Total number of patients: {total_patients} | Processing of this instance: {start_index}-{end_index - 1}")

# ============================== Read unified prompt words ==============================
prompt_path = os.path.join(PROMPT_DIR, PROMPT_FILE)
if not os.path.exists(prompt_path):
    print(f"Error: prompt word file {prompt_path} does not exist")
    sys.exit(1)

with open(prompt_path, 'r', encoding='utf-8') as prompt_f:
    prompt_template = prompt_f.read().strip()

print(f"Unified prompt words loaded: {PROMPT_FILE}")


# ============================== Natural sorting function ==============================
def natural_sort_key(s):
    """
    Natural sorting key function, used to sort strings containing numbers
    """
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', s)]


# ============================== Main processing loop ==============================
for idx in range(start_index, end_index):
    patient_dir_name = all_patient_dirs[idx]
    patient_path = os.path.join(INPUT_DIR, patient_dir_name)

    # Create corresponding output directory
    output_patient_dir = os.path.join(OUTPUT_DIR, patient_dir_name)
    if not os.path.exists(output_patient_dir):
        os.makedirs(output_patient_dir)

    # Input file path (output of the first step)
    input_file_path = os.path.join(output_patient_dir, f"{patient_dir_name}_step1.txt")

    # Output file path (output of the second step)
    output_file_path = os.path.join(output_patient_dir, f"{patient_dir_name}_step2.txt")

    # Check if the first step output exists
    if not os.path.exists(input_file_path):
        print(f"⚠ The first step output of patient {patient_dir_name} does not exist, skip")
        continue

    # Check if it has been processed (skip if the file exists)
    if os.path.exists(output_file_path):
        print(f"✓ Patient {patient_dir_name} processed, skip")
        continue

    print(f"\nProcess patient {idx + 1}/{total_patients}: {patient_dir_name}")

    # Read the output of the first step
    try:
        with open(input_file_path, 'r', encoding='utf-8') as entity_file:
            entity_content = entity_file.read()
        print(f"  Number of entities in the first step: {len(entity_content.splitlines())}")
    except Exception as e:
        print(f"  Reading the first step output failed: {e}")
        continue

    # Build a complete prompt word
    prompt = prompt_template.replace("{{ENTITY_LIST}}", entity_content)

    # Store a collection of all triples (for deduplication)
    all_triples = set()

    # API call retry mechanism
    for attempt in range(MAX_RETRIES):
        try:
            print(f"  API call attempt {attempt + 1}/{MAX_RETRIES}")

            # Interacting with DeepSeek API using OpenAI SDK
            client = OpenAI(
                api_key=API_TOKENS[INSTANCE_INDEX],
                base_url="https://api.deepseek.com"
            )

            # Use non streaming transmission
            response = client.chat.completions.create(
                model="deepseek-reasoner",
                messages=[{"role": "user", "content": prompt}],
                stream=False,
                max_tokens=65536,  # Maximum 64K to prevent truncation
                temperature=0.0
            )

            message_content = response.choices[0].message.content

            print(f"  API response successful, response length: {len(message_content)} characters")
            break

        except Exception as e:
            print(f"  Unexpected error occurred (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            import traceback

            traceback.print_exc()
            if attempt < MAX_RETRIES - 1:
                wait_time = BASE_RETRY_DELAY * (2 ** attempt)
                print(f"  {wait_time:.2f} seconds and retry ..")
                time.sleep(wait_time)
            else:
                print(f"  Maximum retry attempts reached, skip this patient")
                message_content = ""
                break

    # Process API responses and extract triplets
    if message_content:
        # Extract triplets from the response (assuming one triplet per line)
        lines = message_content.strip().split('\n')
        extracted_count = 0
        for line in lines:
            line = line.strip()
            # Match triplet format: (entity type: entity, relationship, entity type: entity) or (entity, attribute type, attribute value)
            if line and line.startswith('(') and line.endswith(')'):
                all_triples.add(line)
                extracted_count += 1
        print(f"  extracted {extracted_count} triplets")
    else:
        print(f"  No valid response received")

    # Write all triplets to the output file
    if all_triples:
        with open(output_file_path, 'w', encoding='utf-8') as output_file:
            for triple in sorted(all_triples):  # Sort for easy reading
                output_file.write(triple + '\n')
        print(f"✓ Patient {patient_dir_name} processing completed, extract {len(all_triples)} triplets")
    else:
        print(f"⚠ Patient {patient_dir_name} did not extract any triplets")

    # API call latency
    print(f"  Wait for {API_DELAY} seconds before making the next API call ..")
    time.sleep(API_DELAY)

print("\nAll patients processed!")