#!/usr/bin/env python3
# Typevote -- Typeform Voting Tool
#
# (C) 2022 All For Eco
# Written by Jan Lindblad <jan.lindblad@protonmail.com>

import sys, getopt, datetime, hashlib, csv, math, re
from logging import debug, warning, error, critical

class Typevote:
  def __init__(self):
    self.salt = str(datetime.datetime.now())
    self.codelen = 12
    self.voters = set()
    self.voterids = {}
    self.orgs = {}
    self.debug = False
    self.results = {}
    self.rogue_voterids = set()
    self.scores = {}
    self.winner = {}
    self.quiz_answers = {}
    self.quiz_answers_regex = {}
    self.quiz_scores = {}
    self.quiz_qchecks = {}
    self.quiz_results = {}
    self.quiz_orgs = {}
    self.voterid_tag = "voterid"
    self.email_tag = "email"
    self.org_tag = "org"
    self.rank = 6

  def salted_hash(self, str_to_hash):
    hashed_str = hashlib.md5((self.salt+str_to_hash).encode()).hexdigest()[:self.codelen]
    return hashed_str

  def add_emails(self, email_file):
    def handle_emails(emails, orgs=[]):
      valid_count, skip_count, dup_count, comma_count = 0, 0, 0, 0
      if len(orgs) < len(emails):
        orgs += ['' for _ in emails]
      for (email_str, org_str) in zip(emails, orgs):
        if "@" in email_str:
          clean_email = email_str.strip().lower()
          clean_org = org_str.strip().upper()
          if "," in clean_email:
            comma_count += 1
          if clean_email not in self.voters:
            valid_count += 1
            self.voters.add(clean_email)
            voter_code = self.salted_hash(clean_email)
            if voter_code in self.voterids:
              critical(f'Hash collision, {clean_email} clashes with {self.voterids[voter_code]} hash "{voter_code}".')
              sys.exit(2)
            self.voterids[voter_code] = clean_email
            self.orgs[voter_code] = clean_org
          else:
            dup_count += 1
        else:
          skip_count += 1
      print(f'{valid_count:4} valid, {comma_count:4} emails with commas, {dup_count:4} duplicate, {skip_count:4} skipped lines, salted as "{self.salt}"\n')

    try:
      csv.register_dialect('skipinitialspace', skipinitialspace=True)
      print(f'==> Reading email file "{email_file}"')
      with open(email_file, newline='') as csvfile:
        emailreader = csv.DictReader(csvfile, dialect='skipinitialspace')
        emails = []
        orgs = []
        for emailrec in emailreader:
          emails += [emailrec[self.email_tag]]
          orgs += [emailrec.get(self.org_tag, '')]
        print(f'==> Treating as CSV format input')
        handle_emails(emails,orgs)
    except:
      print(f'==> Treating as plain email input')
      with open(email_file, "r") as emails:
        handle_emails(emails.readlines())

  def gen_codefile(self, code_file):
    print(f'==> Generating code file "{code_file}"')
    if self.debug:
      for voterid in self.voterids:
        print(f'** {voterid} : {self.voterids[voterid]}')
      print(f'** {len(self.voterids)} voters')
    if code_file:
      with open(code_file, "wt") as f:
        for voterid in self.voterids:
          f.write(f'{self.voterids[voterid]},{self.orgs[voterid]},{voterid}\n')
      print(f'{len(self.voterids)} voter codes written\n')

  def get_votes(self, vote_file):
    def record_quiz_answer(voterid, n, q, response):
      q = q.replace('\n',' ').replace('\r',' ')
      if n in self.quiz_answers:
        if self.quiz_qchecks[n].match(q):
          if self.quiz_answers[n].match(response):
            if self.debug:
              print(f'** {voterid} has correct answer on #{n} and is awarded {self.quiz_scores[n]} points')
            self.quiz_results[voterid] = self.quiz_results.get(voterid,0) + self.quiz_scores[n]
          else:
            if self.debug:
              print(f'** {voterid} has wrong answer on #{n} Q="{q[:10]}" C="{self.quiz_answers_regex[n][:10]}" A="{response[:10]}"')
        else:
          print(f'** >> answerfile has mismatching qcheck on #{n} {q[:10]}')
      else:
        if self.debug:
          print(f'** answerfile has no answer on #{n} {q[:10]}')

    print(f'==> Reading votes from "{vote_file}"')
    votes = {}
    if None in self.voterids:
      critical(f'Illegal voterid in voter database.')
      sys.exit(3)
    typeform_admin_keys = set(('#', 'Network ID', self.voterid_tag, 'Start Date (UTC)', 'Submit Date (UTC)'))
    with open(vote_file, newline='') as csvfile:
      votereader = csv.DictReader(csvfile)
      vote_record_count = 0
      qlist = votereader.fieldnames
      if self.voterid_tag not in qlist:
        critical(f'No "{self.voterid_tag}" column in votefile.')
        sys.exit(4)
      for vote in votereader:
        vote_record_count += 1
        voterid = vote[self.voterid_tag]
        if self.debug:
          print(f'** Reading vote from {voterid}: {vote}')
        if voterid not in votes:
          votes[voterid] = vote
        elif self.debug:
          print(f'** Skipping vote, already have more recent vote from {voterid}')
    responses = {fieldname:{} for fieldname in qlist if fieldname not in typeform_admin_keys}
    for voterid in votes:
      if self.debug:
        print(f'** Processing vote from {voterid}: {votes[voterid]}')
      if voterid not in self.voterids:
        if self.debug:
          print(f'** >> Rogue voterid "{voterid}" <<')
        self.rogue_voterids.add(voterid)
        continue
      for (n,q) in enumerate(qlist):
        if q in typeform_admin_keys:
          continue
        response = votes[voterid].get(q)
        record_quiz_answer(voterid, n, q, response)
        if response in responses[q]:
          responses[q][response] += 1
        else:
          responses[q][response] = 1
    self.results = responses
    if self.debug:
      print(f'** Vote results {self.results}')
    print(f'Read {vote_record_count} records resulting in {len(votes)-len(self.rogue_voterids)} unique, valid votes\n')

  @staticmethod
  def at_least_one_numeric(lst):
    for x in lst:
      try:
        int(x)
        return True
      except:
        pass
    return False

  def gen_result(self, result_file):
    def gen_quiz_results(f):
      f.write('\n\n-----\nQuiz Results:\n')
      org_results = {}
      for voterid in self.quiz_results:
        org = self.orgs[voterid]
        if self.debug:
          print(f"{voterid} in org {org} got {self.quiz_results[voterid]} points")
        if not org in org_results:
          org_results[org] = {}
        org_results[org][voterid] = self.quiz_results[voterid]
      total_score, total_count = 0, 0
      for org in org_results:
        score = sum(org_results[org].values())
        total_score += score
        count = len(org_results[org])
        total_count += count
        avg = score/count
        f.write(f"{org} got {score} points from {count} participants, average is {avg}\n")
      total_avg = total_score / total_count
      f.write(f"\nAverage across all orgs is {total_avg}, total participation {total_count}\n")

    print(f'==> Generating result into "{result_file}"')
    with open(result_file, "wt") as f:
      f.write(f'Results from vote "{self.salt}"\nGenerated on {datetime.datetime.now()}\n\n')

      total_votes = 0
      for i, q in enumerate(self.results, 1):
        total_votes = sum([self.results[q][answer] for answer in self.results[q]])
        if total_votes == 0:
          continue
        scored_q = self.at_least_one_numeric(self.results[q].keys())
        f.write(f'{i}. Question "{q}", total votes {total_votes} (scored {scored_q})\n')
        score = 0
        numeric_votes = 0
        ranked = False
        comma_count = []
        # Check whether this is a ranked choice. If it is, it will have the same number of commas
        # in every response, and they will be many at least as many as the rank
        for response in self.results[q]:
          comma_count += [len([1 for c in response if c == ","])]
        ranked = comma_count[0] > self.rank and len([1 for c in comma_count if c != comma_count[0]]) == 0
        if ranked:
          ranked_options = {option:0 for option in response.split(',')}
          for response in self.results[q]:
            for (weight, option) in enumerate(response.split(',')):
              #print(f"{option} {max(self.rank-weight,0)} {self.results[q][response]}")
              ranked_options[option] += self.results[q][response] * max(self.rank-weight,0)
            #print(f"{ranked_options}")
          self.results[q] = ranked_options
        for response in self.results[q]:
          vote_count = self.results[q][response]
          if response == "":
            response_text = "<BLANK>"
          else: 
            response_text = response 
          try:
            val = int(response)
            score += val*vote_count
            score_text = f'  Score[sum] {val*vote_count}'
            numeric_votes += vote_count
          except:
            score_text = ''
          vote_share = vote_count/total_votes
          if not ranked:
            f.write(f'  {response_text}: {vote_count:4} / {total_votes:4} = {100*vote_share:6.2f}% {score_text}\n')
          else:
            f.write(f'  {response_text}: {vote_count:4}\n')
          if q not in self.winner:
            self.winner[q] = (vote_share, [response_text])
          else:
            (prev_share, prev_text_list) = self.winner[q]
            if prev_share == vote_share:              
              self.winner[q] = (vote_share, prev_text_list + [response_text])
            elif prev_share < vote_share:
              self.winner[q] = (vote_share, [response_text])
        if score:
          avg = score/numeric_votes
          bonus = math.log10(numeric_votes)+1
          mix = avg*bonus
          self.scores[q] = {'sum':score, 'avg':avg, 'mix':mix}
          f.write(f'  Score[sum] = {score}    Score[avg] = {avg:6.2f}    Score[mix] = {mix:6.2f}\n')
        f.write('\n')
      f.write(f'-----\nTotal discarded voterids: {len(self.rogue_voterids)}, ids: {", ".join(self.rogue_voterids)}\n')
      gen_quiz_results(f)

    print(f'Wrote results to {len(self.results)} questions based on {total_votes} valid voters. {len(self.rogue_voterids)} rogue voters discarded.\n')

  def gen_win(self, win_file):
    print(f'==> Generating winners into "{win_file}"')
    with open(win_file, "wt") as f:
      f.write(f'Winners from vote "{self.salt}"\nGenerated on {datetime.datetime.now()}\n')

      if self.scores:
        for method in ['sum']:#, 'avg', 'mix']:
          prev_val = None
          f.write(f'\nWinners by method {method}:\n')
          for i, q in enumerate(sorted(self.scores, key=lambda e: self.scores[e][method], reverse=True),1):
            val = self.scores[q][method]
            if val != prev_val:
              f.write(f'{i:4}. ')
            else:
              f.write(f'      ')
            f.write(f'{q}: {val:6.2f}\n')
            prev_val = val

  def read_quiz_answers(self, answer_file):
    print(f'==> Reading quiz answers from "{answer_file}"')
    with open(answer_file, "r") as f:
      answers = f.readlines()
      for answer in answers:
        answer = answer.strip()
        if answer.startswith("#") or answer == "":
          continue
        [num, score, question_regex, *answer_regex_parts] = answer.split(":")
        answer_regex = ":".join(answer_regex_parts)
        num = int(num)
        self.quiz_answers[num] = re.compile(answer_regex)
        self.quiz_answers_regex[num] = answer_regex
        self.quiz_scores[num] = int(score)
        self.quiz_qchecks[num] = re.compile(question_regex)

  def run_command_line(self, sys_argv=sys.argv):
    def usage(sys_argv):
      print(f'''{sys_argv[0]} [--help] [--debug] [--name <votename>] --emailfile <file> --codefile <file> \\
  [--votefile <file> --resultfile <file> --answerfile <file>]
        -h | --help                 Show this help information
        -d | --debug                Enable debug output
        -n | --name <votename>      Name of the vote, needs to be the same for successive
                                    invocations that pertain to the same vote count
        -e | --emailfile <file>     List of voters' emails, one email address on each line
                                    May be followed by orgname
        -c | --codefile <file>      Generated CSV file with emails and voterids
        -v | --votefile <file>      CSV file with votes cast by voters
        -r | --resultfile <file>    Generated text file with vote count / quiz results
        -w | --winfile <file>       Generated text file with questions ranked by score
        -a | --answerfile <file>    Generate quiz results based on correct answers

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
      opts, args = getopt.getopt(sys_argv[1:],"hdn:e:c:v:r:w:",
        ["help", "debug", "name=", 
         "emailfile=", "codefile=", "votefile=", "resultfile=", "winfile=", 
         "answerfile=",
         "voterid-tag=", "email-tag=", "org-tag="])
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
      elif opt in ("-w", "--winfile"):
        self.gen_win(arg)
      elif opt in ("-a", "--answerfile"):
        self.read_quiz_answers(arg)
      elif opt in ("--voterid-tag"):
        self.voterid_tag = arg
      elif opt in ("--email-tag"):
        self.email_tag = arg
      elif opt in ("--org-tag"):
        self.org_tag = arg
      else:
        critical(f'Unknown option "{opt}".')
        sys.exit(1)

if ( __name__ == "__main__"):
  Typevote().run_command_line()
