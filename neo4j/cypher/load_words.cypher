// words.tsv: word<TAB>first_year
:param batch => $rows;
UNWIND $rows AS row
WITH row
WHERE row.word IS NOT NULL AND row.word <> ""
MERGE (w:Word {text: row.word})
SET w.first_year = CASE
    WHEN row.first_year IS NULL OR row.first_year = "" THEN NULL
    ELSE toInteger(row.first_year)
END;
