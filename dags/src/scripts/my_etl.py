import sys
from awsglue.utils import getResolvedOptions

args = getResolvedOptions(sys.argv, ["JOB_NAME", "input_path", "output_path"])

print(f"Running Glue job: {args['JOB_NAME']}")
print(f"Input: {args['input_path']}")
print(f"Output: {args['output_path']}")