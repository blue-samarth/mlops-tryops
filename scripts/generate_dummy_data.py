import argparse
import numpy as np
import pandas as pd
from pathlib import Path


def generate_normal_data(n_samples: int = 1000, random_state: int = 42) -> pd.DataFrame:
    """
    Generate normal (baseline) synthetic data.
    
    Features:
    - age: 25-70, mean=45, std=10
    - income: 30k-150k, mean=65k, std=20k
    - credit_score: 300-850, mean=680, std=70
    - employment_years: 0-40, mean=10, std=8
    - debt_ratio: 0-1, mean=0.35, std=0.15
    
    Target:
    - approved: Binary (1 = approved, 0 = rejected)
    - Logic: Higher income + credit_score + lower debt_ratio = approval
    """
    np.random.seed(random_state)
    
    # Generate features
    age = np.random.normal(45, 10, n_samples).clip(25, 70)
    income = np.random.normal(65000, 20000, n_samples).clip(30000, 150000)
    credit_score = np.random.normal(680, 70, n_samples).clip(300, 850)
    employment_years = np.random.normal(10, 8, n_samples).clip(0, 40)
    debt_ratio = np.random.normal(0.35, 0.15, n_samples).clip(0, 1)
    
    # Generate target based on features
    # Score combines normalized features
    score = (
        (credit_score - 300) / 550 * 0.4 +
        (income - 30000) / 120000 * 0.3 +
        (1 - debt_ratio) * 0.2 +
        (employment_years / 40) * 0.1
    )
    
    # Add noise and threshold
    score_with_noise = score + np.random.normal(0, 0.1, n_samples)
    approved = (score_with_noise > 0.5).astype(int)
    
    df = pd.DataFrame({
        'age': age.astype(int),
        'income': income.astype(int),
        'credit_score': credit_score.astype(int),
        'employment_years': employment_years.astype(int),
        'debt_ratio': debt_ratio.round(3),
        'approved': approved
    })
    
    return df


def generate_drifted_data(n_samples: int = 1000, random_state: int = 42) -> pd.DataFrame:
    """
    Generate drifted data for testing drift detection.
    
    Drift patterns:
    - age: shifted mean (45 → 52)
    - income: shifted mean (65k → 75k)
    - credit_score: increased variance
    - employment_years: no drift (control)
    - debt_ratio: no drift (control)
    """
    np.random.seed(random_state)
    
    # Generate features with drift
    age = np.random.normal(52, 10, n_samples).clip(25, 70)  # DRIFT: +7 years
    income = np.random.normal(75000, 20000, n_samples).clip(30000, 150000)  # DRIFT: +10k
    credit_score = np.random.normal(680, 95, n_samples).clip(300, 850)  # DRIFT: +25 std
    employment_years = np.random.normal(10, 8, n_samples).clip(0, 40)  # No drift
    debt_ratio = np.random.normal(0.35, 0.15, n_samples).clip(0, 1)  # No drift
    
    # Generate target (same logic)
    score = (
        (credit_score - 300) / 550 * 0.4 +
        (income - 30000) / 120000 * 0.3 +
        (1 - debt_ratio) * 0.2 +
        (employment_years / 40) * 0.1
    )
    
    score_with_noise = score + np.random.normal(0, 0.1, n_samples)
    approved = (score_with_noise > 0.5).astype(int)
    
    df = pd.DataFrame({
        'age': age.astype(int),
        'income': income.astype(int),
        'credit_score': credit_score.astype(int),
        'employment_years': employment_years.astype(int),
        'debt_ratio': debt_ratio.round(3),
        'approved': approved
    })
    
    return df


def generate_categorical_data(n_samples: int = 1000, random_state: int = 42) -> pd.DataFrame:
    """
    Generate data with categorical features for testing categorical drift.
    """
    np.random.seed(random_state)
    
    # Categorical features
    categories = {
        'state': ['CA', 'NY', 'TX', 'FL', 'IL'],
        'education': ['High School', 'Bachelor', 'Master', 'PhD'],
        'job_type': ['Full-time', 'Part-time', 'Contract', 'Self-employed']
    }
    
    state = np.random.choice(categories['state'], n_samples, p=[0.3, 0.25, 0.2, 0.15, 0.1])
    education = np.random.choice(categories['education'], n_samples, p=[0.3, 0.4, 0.2, 0.1])
    job_type = np.random.choice(categories['job_type'], n_samples, p=[0.6, 0.2, 0.15, 0.05])
    
    # Numeric features
    age = np.random.normal(40, 12, n_samples).clip(22, 70).astype(int)
    income = np.random.normal(60000, 25000, n_samples).clip(25000, 200000).astype(int)
    
    # Target influenced by categories
    score = np.zeros(n_samples)
    score += (education == 'PhD') * 0.3
    score += (education == 'Master') * 0.2
    score += (job_type == 'Full-time') * 0.2
    score += (state == 'CA') * 0.1
    score += (income / 200000) * 0.3
    score += np.random.normal(0, 0.15, n_samples)
    
    approved = (score > 0.4).astype(int)
    
    df = pd.DataFrame({
        'age': age,
        'income': income,
        'state': state,
        'education': education,
        'job_type': job_type,
        'approved': approved
    })
    
    return df


def main():
    parser = argparse.ArgumentParser(description='Generate synthetic training data')
    parser.add_argument('--output', type=str, required=True, help='Output CSV file path')
    parser.add_argument('--samples', type=int, default=1000, help='Number of samples to generate')
    parser.add_argument('--drift', action='store_true', help='Generate drifted data')
    parser.add_argument('--categorical', action='store_true', help='Include categorical features')
    parser.add_argument('--seed', type=int, default=42, help='Random seed')
    
    args = parser.parse_args()
    
    # Create output directory
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Generate data
    if args.categorical:
        df = generate_categorical_data(args.samples, args.seed)
        print(f"Generated {args.samples} samples with categorical features")
    elif args.drift:
        df = generate_drifted_data(args.samples, args.seed)
        print(f"Generated {args.samples} drifted samples")
        print(f"  - age: mean shifted 45 → 52")
        print(f"  - income: mean shifted 65k → 75k")
        print(f"  - credit_score: std increased 70 → 95")
    else:
        df = generate_normal_data(args.samples, args.seed)
        print(f"Generated {args.samples} normal samples")
    
    # Save
    df.to_csv(output_path, index=False)
    print(f"\nSaved to: {output_path}")
    print(f"\nDataset summary:")
    print(df.describe())
    print(f"\nTarget distribution:")
    print(df['approved'].value_counts())


if __name__ == '__main__':
    main()
