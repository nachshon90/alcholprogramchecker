---
title: Alcohol Label Compliance Checker
emoji: 🍷
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 8080
pinned: false
short_description: Check alcohol labels against federal 27 CFR labelling rules
---

# Alcohol Label Compliance Checker

Enter your company and product details, upload one or two pictures of the
label, and this checks them against the federal labelling rules in 27 CFR -
brand name, class/type, alcohol content, net contents, bottler name and
address, country of origin, sulfites, and the Government Health Warning.

**This Space is password protected.** Set `LABELCHECK_PASSWORD` as a Space
secret; the app refuses to start without one.

OCR runs inside this container using Tesseract. No third-party vision API is
used and no image is written to disk. Note that a hosted copy still means
your pictures travel over the network to this server, which is why the tool
is designed to be run locally when the artwork is confidential.

Source and full documentation:
<https://github.com/nachshon90/alcholprogramchecker>
