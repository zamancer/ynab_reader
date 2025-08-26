# Payment Summary feature

This document will outline how I'm planning to implement the payment feature.

## Context

This tool is meant for my personal use, keeping track of my expenses among two distinct budgets, one for my regular expenses, and another one meant for investments, such as my family funds, my retirement plan, etc. Those are irregular, meaning sometimes I invest funds, sometimes I just save the funds and keep them stored in a CETES account or similar until the time is right.

The challenge I have is, the current budgeting system I have (powered by YNAB) is somewhat complex to navigate, making it hard for me to know what savings and debit accounts I can use to pay my credit cards and other deposits on a monthly basis. The complexity is added when some credit cards are shared between the two budgets, where some expenses should be covered by A source and some others (likely from the other budget) should be covered from B source.

I am thinking of solving this problem by introducing the idea of a 1 to N relationship between the credit cards and my debit sources through this repository.

Ultimately, the payment summary should be an easy to follow recipe of what account should be moving what money where, and it should be loaded on a new page of the spreadsheet (Ledger) we use as source of truth, such that I can monthly use that to easily sit down in a quick 20 minute session and perform all my transactions such that payments are done.

## Detailed Design

In this section, I will describe the way I am planning to solve this problem at a high-level idea.

### Summary

This will contain the high-level summary (with steps) of what we'll do to face and solve the problem.

### Technical Design

This section will hold the information about the chosen alternative (from the winning Alternatives section), which is the recommended path forward for tackling the problem. This section will have more intrisicate details such as some code samples (high level) and the communication path (sequence) between the components which will solve the problem. The idea is to break it down so this is digestable information for the audience, as well as starts a sequence of work we can track for incrementally tracking the progress of the project.

## Alternatives

Here, I'll document at least two different alternatives for solving this problem.
