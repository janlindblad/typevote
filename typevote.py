#!/usr/bin/env python3
# Typevote -- Typeform Voting Tool
#
# (C) 2022 All For Eco
# Written by Jan Lindblad <jan.lindblad@protonmail.com>

import sys, getopt, datetime, hashlib, csv
from logging import debug, warning, error, critical
from typing import Type

class Typevote:
  def __init__(self):
    self.salt = str(datetime.datetime.now())
    self.codelen = 12
    self.voters = set()
    self.voterids = {}
    self.debug = False
    self.results = {}
    self.rogue_voterids = set()

  def salted_hash(self, str_to_hash):
    hashed_str = hashlib.md5((self.salt+str_to_hash).encode()).hexdigest()[:self.codelen]
    return hashed_str

  def add_emails(self, email_file):
    print(f'==> Reading email file "{email_file}"')
    with open(email_file, "r") as emails:
      valid_count, skip_count, dup_count = 0, 0, 0
      for line in emails.readlines():
        if "@" in line:
          clean_email = line.strip()
          if clean_email not in self.voters:
            valid_count += 1
            self.voters.add(clean_email)
            voter_code = self.salted_hash(clean_email)
            if voter_code in self.voterids:
              critical(f'Hash collision, {clean_email} clashes with {self.voterids[voter_code]} hash "{voter_code}".')
              sys.exit(2)
            self.voterids[voter_code] = clean_email
          else:
            dup_count += 1
        else:
          skip_count += 1
      print(f'{valid_count:4} valid, {dup_count:4} duplicate, {skip_count:4} skipped lines, salted as "{self.salt}"\n')

  def gen_codefile(self, code_file):
    print(f'==> Generating code file "{code_file}"')
    if self.debug:
      for voterid in self.voterids:
        print(f'** {voterid} : {self.voterids[voterid]}')
      print(f'** {len(self.voterids)} voters')
    if code_file:
      with open(code_file, "wt") as f:
        for voterid in self.voterids:
          f.write(f'{self.voterids[voterid]},{voterid}\n')
      print(f'{len(self.voterids)} voter codes written\n')

  def get_votes(self, vote_file):
    print(f'==> Reading votes from "{vote_file}"')
    votes = {}
    if None in self.voterids:
      critical(f'Illegal voterid in voter database.')
      sys.exit(3)
    with open(vote_file, newline='') as csvfile:
      votereader = csv.DictReader(csvfile)
      vote_record_count = 0
      qlist = votereader.fieldnames
      if "voterid" not in qlist:
        critical(f'No voterid column in votefile.')
        sys.exit(4)
      for vote in votereader:
        vote_record_count += 1
        voterid = vote['voterid']
        if self.debug:
          print(f'** Reading vote from {voterid}: {vote}')
        votes[voterid] = vote
    responses = {fieldname:{} for fieldname in qlist}
    for voterid in votes:
      if self.debug:
        print(f'** Processing vote from {voterid}: {votes[voterid]}')
      if voterid not in self.voterids:
        if self.debug:
          print(f'** >> Rogue voterid "{voterid}" <<')
        self.rogue_voterids.add(voterid)
        continue
      for q in qlist:
        response = votes[voterid].get(q)
        if response in responses[q]:
          responses[q][response] += 1
        else:
          responses[q][response] = 1
    self.results = responses
    if self.debug:
      print(f'** Vote results {self.results}')
    print(f'Read {vote_record_count} records resulting in {len(votes)} unique, valid votes\n')

  def gen_result(self, result_file):
    print(f'==> Generating result into "{result_file}"')
    with open(result_file, "wt") as f:
      f.write(f'Results from vote "{self.salt}"\nGenerated on {datetime.datetime.now()}\n\n')

      for i, q in enumerate(self.results):
        total_votes = sum([self.results[q][answer] for answer in self.results[q]])
        if total_votes == 0:
          continue
        f.write(f'{i}. Question "{q}", total votes {total_votes}\n')
        for response in self.results[q]:
          response_text = response if response != "" else "<BLANK>"
          vote_count = self.results[q][response]
          f.write(f'  {response_text}: {vote_count} / {total_votes} = {100*vote_count/total_votes:6.2f}%\n')
        f.write('\n')
      f.write(f'-----\nTotal discarded voterids: {len(self.rogue_voterids)}, ids: {", ".join(self.rogue_voterids)}\n')
    print(f'Wrote results to {len(self.results)} questions based on {total_votes} valid voters. {len(self.rogue_voterids)} rogue voters discarded.\n')

  def run_command_line(self, sys_argv=sys.argv):
    def usage(sys_argv):
      print(f'''{sys_argv[0]} [--help] [--debug] [--name <votename>] --emailfile <file> --codefile <file> \\
  [--votefile <file> --resultfile <file>]
        -h | --help                 Show this help information
        -d | --debug                Enable debug output
        -n | --name <votename>      Name of the vote, needs to be the same for successive
                                    invocations that pertain to the same vote count
        -e | --emailfile <file>     List of voters' emails, one email address on each line
        -c | --codefile <file>      Generated CSV file with emails and voterids
        -v | --votefile <file>      CSV file with votes cast by voters
        -r | --resultfile <file>    Generated text file with vote count

        For example, to generate a CSV file with voterids to upload to a mass mailer
        based on a list of emails in voters1.txt and voters2.txt for a vote on favorite color:
        {sys_argv[0]} -n fav-color -e voters1.txt -e voters2.txt --codefile codes.csv

        Then later, when the voting has completed, run again with the same parameters, but
        also add the CSV file with cast votes cast-votes-12feb.csv, and generate a final 
        count in fav-col-results.txt:
        {sys_argv[0]} -n fav-color -e voters1.txt -e voters2.txt --codefile codes.csv \\
          --votefile cast-votes-12feb.csv --resultfile fav-col-results.txt
      ''')
    debug = False
    try:
      opts, args = getopt.getopt(sys_argv[1:],"hdn:e:c:v:r:",
        ["help", "debug", "name=", 
         "emailfile=", "codefile=", "votefile=", "resultfile="])
    except getopt.GetoptError:
      usage(sys_argv)
      sys.exit(2)
    for opt, arg in opts:
      if self.debug:
        print(f'** Processing {opt} {arg}')
      if opt in ('-h', '--help'):
        usage(sys_argv)
        sys.exit()
      elif opt in ("-d", "--debug"):
        self.debug = True
      elif opt in ("-n", "--name"):
        self.salt = arg
      elif opt in ("-e", "--emailfile"):
        self.add_emails(arg)
      elif opt in ("-c", "--codefile"):
        self.gen_codefile(arg)
      elif opt in ("-v", "--votefile"):
        self.get_votes(arg)
      elif opt in ("-r", "--resultfile"):
        self.gen_result(arg)
      else:
        critical(f'Unknown option "{opt}".')
        sys.exit(1)

if ( __name__ == "__main__"):
  Typevote().run_command_line()