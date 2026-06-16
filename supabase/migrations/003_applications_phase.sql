-- Add columns to support automated job applications and cover letter generation

ALTER TABLE public.job_matches 
ADD COLUMN IF NOT EXISTS cover_letter TEXT;

ALTER TABLE public.job_matches 
ADD COLUMN IF NOT EXISTS application_qa JSONB;
