# Restricted anonymized LH2 model-validation evidence

PRISM now records the external `sci_minimal_release_packet.json` as a
digest-bound, restricted model-validation record. The packet describes an
anonymized LH2 storage, venting, and vaporization model and reports blind,
held-out validation for independently scored observed units.

The released aggregate contains 12 declared units, of which 3 are independently
scored. Their macro accuracy is 95.4155462264504 percent. The remaining units
are not imputed, and the full-system target is explicitly false. Raw historian
records, facility drawings, instrument tags, and operating logs are not
publicly released.

This evidence supports the credibility review of the process-state model only.
It does not qualify an accident-release provider, create a literature frequency,
or close the facility IR/F-N assessment. PRISM therefore keeps all four
promotion flags false: provider packet, frequency, facility QRA, and independent
end-to-end physical validation. A strict physical-validation claim remains
false until an independently reviewed, facility-relevant release and consequence
chain is available.

The reproducible, non-sensitive summary is stored at
`results/20261115/external_anonymized_model_validation_summary.json`. The summary
contains the source SHA-256 digest and the publication claim boundary without
copying private raw data into the repository.
