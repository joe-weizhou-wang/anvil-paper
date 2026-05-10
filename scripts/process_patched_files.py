#############################################
# iterates over each patched magma file and #
# processes the file by defining/undefining #
# magma preprocessor directives to create a #
# buggy and patched version of each patched #
# file, collects line numbers of buggy and  #
# patched lines                             #
#############################################

import os
import subprocess
import json

def collect_patched_files(targets_dir):
  patched_files = []
  for target in os.listdir(targets_dir):
    target_dir = os.path.join(targets_dir, target)
    patches = subprocess.Popen(
      ['find', '{}/patches/bugs'.format(target_dir), '-name', '*.patch'],
      stdout=subprocess.PIPE,
      stderr=subprocess.DEVNULL
    ).communicate()[0].rstrip().decode('utf-8').split('\n')

    for patch in patches:
      with open(patch) as f:
        cur_file = ""
        for line in f:
          if line.startswith("---"):
            patched_file = "{}/repo/{}".format(target_dir, line.split(' ')[1][2:].rstrip())
            patched_files.append(patched_file)
          if line.startswith("+++"):
            patched_file = "{}/repo/{}".format(target_dir, line.split(' ')[1][2:].rstrip())
            assert(patched_file == patched_files[-1])
          cur_file += line.strip()
  return patched_files

def process_files(patched_files,
                  repo_dir,
                  buggy_output_dir,
                  patched_output_dir,
                  magma_output_dir):
  cve_lines = {}
  added_lines = {}
  for patched_file in patched_files:
    path_suffix = patched_file.split("targets/")[1].replace('/', '_')
    buggy_output_file = "{}/{}".format(buggy_output_dir, path_suffix)
    patched_output_file = "{}/{}".format(patched_output_dir, path_suffix)
    magma_output_file = "{}/{}".format(magma_output_dir, path_suffix)
    unifdef = "{}/utils/unifdef-2.12/unifdef".format(repo_dir)

    with open(buggy_output_file, 'w') as buggy_f_out, \
         open(patched_output_file, 'w') as patched_f_out:

      cve_lines[patched_file] = {
        "file_with_cve" : buggy_output_file,
        "file_with_fix" : patched_output_file,
        "cve_lines" : [],
        "patch_lines" : []
      }

      added_lines[buggy_output_file] = []

      if not os.path.isfile(unifdef):
        print("init_repos.sh must be run before this script!")
        exit(1)

      subprocess.call([unifdef, "-UMAGMA_ENABLE_FIXES",
                                "-UENABLE_MAGMA_FIXES",
                                "-UMAGMA_ENABLE_CANARIES",
                                patched_file],
                      stdout=buggy_f_out) 
      subprocess.call([unifdef, "-DMAGMA_ENABLE_FIXES",
                                "-DENABLE_MAGMA_FIXES",
                                "-UMAGMA_ENABLE_CANARIES",
                                patched_file],
                      stdout=patched_f_out) 
      subprocess.call(["cp", patched_file, magma_output_file]) 
      subprocess.call(["sed", "-i", "/^[[:space:]]*$/d", buggy_output_file])
      subprocess.call(["sed", "-i", "/^[[:space:]]*$/d", patched_output_file])
      subprocess.call(["sed", "-i", "/^[[:space:]]*$/d", magma_output_file])

      diff_out = subprocess.run(["diff", buggy_output_file, patched_output_file],
                                capture_output=True, text=True)
      diff_lines = diff_out.stdout.split('\n')
      for line in diff_lines:
        stripped_line = line.strip()
        if not stripped_line or not stripped_line[0].isdigit():
          continue

        if 'a' in stripped_line:
          buggy_lines, patched_lines = stripped_line.split('a')
          if ',' in buggy_lines:
            start, end = buggy_lines.split(',')
            cve_lines[patched_file]["cve_lines"].append((start, end))
            added_lines[buggy_output_file].append(start).append(end)
          else:
            cve_lines[patched_file]["cve_lines"].append(buggy_lines)
            added_lines[buggy_output_file].append(buggy_lines)
          if ',' in patched_lines:
            start, end = patched_lines.split(',')
            cve_lines[patched_file]["patch_lines"].append((start, end))
          else:
            cve_lines[patched_file]["patch_lines"].append(patched_lines)

        elif 'c' in stripped_line:
          buggy_lines, patched_lines = stripped_line.split('c')
          if ',' in buggy_lines:
            start, end = buggy_lines.split(',')
            cve_lines[patched_file]["cve_lines"].append((start, end))
          else:
            cve_lines[patched_file]["cve_lines"].append(buggy_lines)
          if ',' in patched_lines:
            start, end = patched_lines.split(',')
            cve_lines[patched_file]["patch_lines"].append((start, end))
          else:
            cve_lines[patched_file]["patch_lines"].append(patched_lines)

        elif 'd' in stripped_line:
          buggy_lines, patched_lines = stripped_line.split('d')
          if ',' in buggy_lines:
            start, end = buggy_lines.split(',')
            cve_lines[patched_file]["cve_lines"].append((start, end))
          else:
            cve_lines[patched_file]["cve_lines"].append(buggy_lines)
          if ',' in patched_lines:
            start, end = patched_lines.split(',')
            cve_lines[patched_file]["patch_lines"].append((start, end))
          else:
            cve_lines[patched_file]["patch_lines"].append(patched_lines)

        else:
          print("This should not happen...")
          exit(1)

  # with open(repo_dir + '/added_lines.json', 'w') as f:
  #   json.dump(added_lines, f, indent=2)


  return cve_lines

repo_dir = subprocess.Popen(
  ['git', 'rev-parse', '--show-toplevel'],
  stdout=subprocess.PIPE
).communicate()[0].rstrip().decode('utf-8') + '/data'

cve_targets_dir = repo_dir + "/cve-targets"
patched_targets_dir = repo_dir + "/fixed-targets"
magma_targets_dir = repo_dir + "/magma-targets"
targets_dir = repo_dir + "/magma/targets"

patched_files = collect_patched_files(targets_dir)
cve_lines = process_files(patched_files,
                          repo_dir,
                          cve_targets_dir,
                          patched_targets_dir,
                          magma_targets_dir)

with open(repo_dir + '/magma_bugs.json', 'w') as f:
  json.dump(cve_lines, f, indent=2)
