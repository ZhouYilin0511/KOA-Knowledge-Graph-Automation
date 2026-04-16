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
PROMPT_FILE = "KOA_step3_知识融合提示词.txt"

# API call parameters
API_DELAY = 15
MAX_RETRIES = 5
BASE_RETRY_DELAY = 1
BATCH_THRESHOLD = 300  # Threshold for batch processing

# ============================== Command line parameter processing ==============================
if len(sys.argv) < 2:
    print("Please specify instance index (0 to total instances -1)")
    sys.exit(1)

try:
    INSTANCE_INDEX = int(sys.argv[1])
    TOTAL_INSTANCES = len(API_TOKENS)

    if INSTANCE_INDEX < 0 or INSTANCE_INDEX >= TOTAL_INSTANCES:
        print(f"Error: Instance index must be between 0 and{TOTAL_INSTANCES - 1}")
        sys.exit(1)

    print(f"Current instance index: {INSTANCE_INDEX}/{TOTAL_INSTANCES - 1}")
    print(f"The API key used for print (f) is: ..{API_TOKENS[INSTANCE_INDEX][-6:]}")

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

print(f"Uniform prompt loaded:  {PROMPT_FILE}")


# ============================== helper function ==============================
def extract_triples_from_response(response_text):
    """
    Extract triplets from API responses without deduplication, maintaining the original order
    """
    triples = []
    lines = response_text.strip().split('\n')

    for line in lines:
        line = line.strip()
        # Match triplet format: (entity type: entity name, relationship, entity type: entity name) or (entity type: entity name, attribute, attribute value)
        if line and line.startswith('(') and line.endswith(')'):
            triples.append(line)

    return triples


def extract_entity_from_triple(triple):
    """
    Extract subject entities from triplets
    """
    match = re.match(r'\(([^,]+),', triple)
    if match:
        return match.group(1)
    return None


def find_safe_cut_point(triples, start_idx, target_size):
    """
    Find a safe cutting point to avoid cutting consecutive triplets of the same entity
    """
    n = len(triples)
    end_idx = min(start_idx + target_size, n)

    # If it is already the last batch, return directly
    if end_idx == n:
        return end_idx

    # First, try to find the entity boundary near the target size
    for i in range(end_idx - 1, start_idx, -1):
        # Check if the current line and the next line are the same entity
        current_triple = triples[i]
        next_triple = triples[i + 1] if i + 1 < n else ""

        current_entity = extract_entity_from_triple(current_triple)
        next_entity = extract_entity_from_triple(next_triple)

        # If the next line is a different entity or there is no next line, this is the safe cutting point
        if not next_entity or current_entity != next_entity:
            return i + 1

    # If no obvious boundary is found, use the original cutting point
    return end_idx


def create_batches_with_safe_cuts(triples, batch_threshold=400):
    """
    Create batches to ensure cutting at entity boundaries
    """
    batches = []
    i = 0
    n = len(triples)

    while i < n:
        cut_point = find_safe_cut_point(triples, i, batch_threshold)
        batch = triples[i:cut_point]

        if batch:  # Only add non empty batches
            batches.append(batch)

        i = cut_point

    return batches


# ============================== Main processing loop ==============================
for idx in range(start_index, end_index):
    patient_dir_name = all_patient_dirs[idx]
    patient_path = os.path.join(INPUT_DIR, patient_dir_name)

    # Create corresponding output directory
    output_patient_dir = os.path.join(OUTPUT_DIR, patient_dir_name)
    if not os.path.exists(output_patient_dir):
        os.makedirs(output_patient_dir)

    # Input file path (output of the second step)
    input_file_path = os.path.join(output_patient_dir, f"{patient_dir_name}_step2.txt")

    # Output file path (output of the third step)
    output_file_path = os.path.join(output_patient_dir, f"{patient_dir_name}_step3.txt")

    # Check if the second step output exists
    if not os.path.exists(input_file_path):
        print(f"⚠ The second step output of patient {patient_dir_name} does not exist, skip")
        continue

    # Check if it has been processed (skip if the file exists)
    if os.path.exists(output_file_path):
        print(f"✓ Patient {patient_dir_name} processed, skip")
        continue

    print(f"\nProcess patient {idx + 1}/{total_patients}: {patient_dir_name}")

    # Read the output of the second step
    try:
        with open(input_file_path, 'r', encoding='utf-8') as triple_file:
            # Read all rows without removing empty lines, maintaining the original number of rows
            all_lines = triple_file.readlines()
            # Remove line breaks at the end of each line
            input_triples = [line.rstrip('\n') for line in all_lines if line.strip()]

        print(f"  Step 2: Number of triples: {len(input_triples)}")

        # Check if it needs to be done in batches
        if len(input_triples) <= BATCH_THRESHOLD:
            print(f"  If the number of triples is less than or equal to{BATCH_THRESHOLD}, process directly")
            batches = [input_triples]
            # batch_files = []  # Used to store batch file names
        else:
            # Use safe cutting in batches
            print(f"  If the number of triples is greater than{BATCH_THRESHOLD}, use secure splitting in batches")
            batches = create_batches_with_safe_cuts(input_triples, BATCH_THRESHOLD)
            # batch_files = []  # Used to store batch file names

            print(f"  divided into {len(batches)} batches")
            for i, batch in enumerate(batches):
                print(f"    Batch {i + 1}: {len(batch)} rows")

    except Exception as e:
        print(f"  Read second step output failed: {e}")
        continue

    # Initialize the client
    client = OpenAI(
        api_key=API_TOKENS[INSTANCE_INDEX],
        base_url="https://api.deepseek.com"
    )

    # Store the fusion results of all batches
    all_fused_triples = []

    # Process each batch
    for batch_idx, batch_triples in enumerate(batches):
        print(f"\n  processing batch {batch_idx + 1}/{len(batches)}")
        print(f"    Batch line count: {len(batch_triples)}")

        # Build the triplet string for the current batch
        triple_list = "\n".join(batch_triples)

        # Build a complete prompt word
        prompt = prompt_template.replace("{{TRIPLE_LIST}}", triple_list)

        # API call retry mechanism
        message_content = ""
        for attempt in range(MAX_RETRIES):
            try:
                print(f"    API call attempt {attempt + 1}/{MAX_RETRIES}")

                # Use non streaming transmission
                response = client.chat.completions.create(
                    model="deepseek-reasoner",
                    messages=[{"role": "user", "content": prompt}],
                    stream=False,
                    max_tokens=65536,  # Maximum 64K to prevent truncation
                    temperature=0.0
                )

                message_content = response.choices[0].message.content
                print(f"    API response successful, response length: {len(message_content)} characters")
                break

            except Exception as e:
                print(f"    An unexpected error occurred (attempting {attempt + 1}/{MAX_RETRIES}): {e}")
                import traceback

                traceback.print_exc()

                if attempt < MAX_RETRIES - 1:
                    wait_time = BASE_RETRY_DELAY * (2 ** attempt)
                    print(f"    {wait_time:.2f}seconds and retry ..")
                    time.sleep(wait_time)
                else:
                    print(f"    The maximum retry count has been reached, skipping this batch")
                    message_content = ""
                    break

        # Extract the fused triplet
        if message_content:
            batch_fused_triples = extract_triples_from_response(message_content)

            # # If processing in batches, save the output file of the current batch first
            # if len(batches) > 1:
            #     batch_output_path = os.path.join(
            #         output_patient_dir,
            #         f"{patient_dir_name}_step3_batch{batch_idx + 1}_{len(batch_fused_triples)}个.txt"
            #     )
            #
            #     with open(batch_output_path, 'w', encoding='utf-8') as batch_file:
            #         for triple in batch_fused_triples:
            #             batch_file.write(triple + '\n')
            #
            #     batch_files.append(batch_output_path)
            #     print(f"    Batch {batch_idx + 1} processing completed, saved to: {os.path.basename(batch_output_path)}")

            all_fused_triples.extend(batch_fused_triples)
            print(f"    Batch {batch_idx + 1} extracted {len(batch_fused_triples)} fused triplets")
            print(f"    Accumulated fusion triplet: {len(all_fused_triples)}")
        else:
            print(f"    Batch {batch_idx + 1} did not receive a valid response")

        # Delay between batches
        if batch_idx < len(batches) - 1:
            print(f"    Wait for {API_DELAY} seconds before proceeding to the next batch of processing ..")
            time.sleep(API_DELAY)

    # Write the fused triplet into the final step3.txt file
    if all_fused_triples:
        with open(output_file_path, 'w', encoding='utf-8') as output_file:
            for triple in all_fused_triples:
                output_file.write(triple + '\n')

        print(f"✓ Patient {patient_dir_name} processing completed")
        print(f"  The total output is {len(all_fused_triples)} fused triplets to {os.path.basename(output_file_path)}")

        # # If processed in batches, display batch file information
        # if len(batches) > 1:
        #     print(f"  Intermediate files processed in batches:")
        #     for batch_file in batch_files:
        #         print(f"    - {os.path.basename(batch_file)}")
    else:
        print(f"⚠ Patient {patient_dir_name} did not extract any fused triplets")

    # Delay between patients
    print(f"  Wait for {API_DELAY} seconds before proceeding to the next patient treatment ..")
    time.sleep(API_DELAY)

print("\nAll patients have been processed!")