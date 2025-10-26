use std::collections::HashSet;
use once_cell::sync::Lazy;

const MIN_TEXT_LENGTH: usize = 100;
const MIN_LETTER_RATIO: f32 = 0.3;
const MIN_WORDS: usize = 20;
const MIN_RECOGNIZABLE_WORDS: usize = 5;
const MAX_SINGLE_CHAR_RATIO: f32 = 0.4;

// Common civic/government words for validation
static CIVIC_WORDS: Lazy<HashSet<&'static str>> = Lazy::new(|| {
    [
        // Common words
        "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by",
        // Civic terms
        "council", "city", "meeting", "agenda", "item", "public", "comment", "session",
        "board", "commission", "appointment", "ordinance", "resolution", "budget",
        "planning", "zoning", "development", "traffic", "safety", "park", "library",
        "police", "fire", "emergency", "infrastructure", "project", "contract",
        "approval", "review", "hearing", "vote", "motion", "approve", "deny",
        "discussion", "report", "presentation", "staff", "department", "mayor",
        "member", "chair", "chairman", "chairwoman", "minutes", "action", "adopt",
    ]
    .iter()
    .copied()
    .collect()
});

pub struct TextValidator {
    min_length: usize,
    min_letter_ratio: f32,
    min_words: usize,
    min_recognizable: usize,
    max_single_char_ratio: f32,
}

impl TextValidator {
    pub fn new() -> Self {
        Self {
            min_length: MIN_TEXT_LENGTH,
            min_letter_ratio: MIN_LETTER_RATIO,
            min_words: MIN_WORDS,
            min_recognizable: MIN_RECOGNIZABLE_WORDS,
            max_single_char_ratio: MAX_SINGLE_CHAR_RATIO,
        }
    }

    /// Validate text quality
    /// Returns true if text passes all quality checks
    /// Confidence: 8/10 - Heuristics work well for civic documents
    pub fn is_good_quality(&self, text: &str) -> bool {
        // Check 1: Minimum length
        if text.len() < self.min_length {
            tracing::debug!(
                "Quality check FAILED: Text too short ({} chars, need >= {})",
                text.len(),
                self.min_length
            );
            return false;
        }

        // Check 2: Letter ratio
        let letters = text.chars().filter(|c| c.is_alphabetic()).count();
        let total_chars = text.len();

        if total_chars == 0 {
            tracing::debug!("Quality check FAILED: Zero characters");
            return false;
        }

        let letter_ratio = letters as f32 / total_chars as f32;
        if letter_ratio < self.min_letter_ratio {
            tracing::warn!(
                "Quality check FAILED: Letter ratio too low ({:.2}%, need >= {:.2}%)",
                letter_ratio * 100.0,
                self.min_letter_ratio * 100.0
            );
            return false;
        }

        // Check 3: Word count
        let words: Vec<&str> = text.split_whitespace().collect();
        if words.len() < self.min_words {
            tracing::warn!(
                "Quality check FAILED: Too few words ({}, need >= {})",
                words.len(),
                self.min_words
            );
            return false;
        }

        // Check 4: Recognizable words
        let sample_words: Vec<&str> = words.iter().take(100).copied().collect();
        let recognizable = sample_words
            .iter()
            .filter(|word| {
                let cleaned = word
                    .trim_matches(|c: char| !c.is_alphabetic())
                    .to_lowercase();
                CIVIC_WORDS.contains(cleaned.as_str())
            })
            .count();

        if sample_words.len() >= 50 && recognizable < self.min_recognizable {
            tracing::warn!(
                "Quality check FAILED: Too few recognizable words ({}/{})",
                recognizable,
                sample_words.len()
            );
            return false;
        }

        // Check 5: Excessive single-character words
        let single_chars = sample_words
            .iter()
            .filter(|word| word.len() == 1)
            .count();

        let single_char_ratio = single_chars as f32 / sample_words.len() as f32;
        if sample_words.len() >= 50 && single_char_ratio > self.max_single_char_ratio {
            tracing::warn!(
                "Quality check FAILED: Too many single-char words ({:.1}%)",
                single_char_ratio * 100.0
            );
            return false;
        }

        tracing::debug!(
            "Quality check PASSED: {} chars, {} words, {:.1}% letters, {}/{} recognizable",
            total_chars,
            words.len(),
            letter_ratio * 100.0,
            recognizable,
            sample_words.len()
        );

        true
    }

    pub fn get_stats(&self, text: &str) -> TextStats {
        let letters = text.chars().filter(|c| c.is_alphabetic()).count();
        let total_chars = text.len();
        let words: Vec<&str> = text.split_whitespace().collect();

        let sample_words: Vec<&str> = words.iter().take(100).copied().collect();
        let recognizable = sample_words
            .iter()
            .filter(|word| {
                let cleaned = word
                    .trim_matches(|c: char| !c.is_alphabetic())
                    .to_lowercase();
                CIVIC_WORDS.contains(cleaned.as_str())
            })
            .count();

        TextStats {
            total_chars,
            letter_count: letters,
            letter_ratio: if total_chars > 0 {
                letters as f32 / total_chars as f32
            } else {
                0.0
            },
            word_count: words.len(),
            recognizable_words: recognizable,
        }
    }
}

impl Default for TextValidator {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug)]
pub struct TextStats {
    pub total_chars: usize,
    pub letter_count: usize,
    pub letter_ratio: f32,
    pub word_count: usize,
    pub recognizable_words: usize,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_good_quality_text() {
        let validator = TextValidator::new();

        let good_text = "The city council meeting agenda includes discussion of the new zoning ordinance. \
                        The planning commission will review the budget allocation for infrastructure projects. \
                        Public comment is encouraged at the hearing.";

        assert!(validator.is_good_quality(good_text));
    }

    #[test]
    fn test_too_short() {
        let validator = TextValidator::new();
        let short_text = "Too short";
        assert!(!validator.is_good_quality(short_text));
    }

    #[test]
    fn test_gibberish() {
        let validator = TextValidator::new();
        let gibberish = "xyzabc qwerty asdfgh zxcvbn mnbvcx qweasd zxcasd qwezxc asdzxc qweasdzxc \
                        mnbvcxzasd qwertyzxc asdfghmnb vcxzaqwer tyuiopasdf ghjklzxcv bnmqwert yuiopasdf";
        assert!(!validator.is_good_quality(gibberish));
    }

    #[test]
    fn test_stats() {
        let validator = TextValidator::new();
        let text = "The city council meeting agenda includes discussion";
        let stats = validator.get_stats(text);

        assert!(stats.total_chars > 0);
        assert!(stats.word_count > 0);
        assert!(stats.letter_ratio > 0.5);
    }
}
