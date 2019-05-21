import argparse
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument('--output_path', type=str, default='./jobs/todo/submit_job.sh',
                    help='Path of training file')
parser.add_argument('--spec_dir', type=str, required=True,
                        help='location where raw spectra are stored')
parser.add_argument('--script', type=str, required=True,
                        help='path to spectra processing python script')
parser.add_argument('--save_dir', type=str, required=True,
                    help='temporary location where processed spectra will be saved')
parser.add_argument('--obs_wave_file', type=str, required=True,
                    help='path of observational wavelength grid')
parser.add_argument('--num_spec', type=int, required=True,
                    help='max number of spectra to store in save_dir')
parser.add_argument('--synth_wave_file', type=str, default=None,
                    help='path of synthetic wavelength grid (only needed if in separate file)')
parser.add_argument('-g', '--grid', type=str, default='phoenix',
                    help='name of spectral grid to be used')
parser.add_argument('-b', '--batch_size', type=int, default=32,
                    help='number of spectra per batch')
parser.add_argument('-n', '--noise', type=float, default=0.07,
                    help='maximum fractional noise')
parser.add_argument('-r', '--resolution', type=int, default=47000,
                    help='instrumental resolution to convolve to')
parser.add_argument('-vrad', '--radial_vel', type=float, default=200.,
                    help='maximum radial velocity (km/s)')
parser.add_argument('-vrot', '--rotational_vel', type=float, default=70.,
                    help='maximum rotational velocity (km/s)')
parser.add_argument('--max_teff', type=float, default=np.Inf,
                    help='maximum temperature (K)')
parser.add_argument('--min_teff', type=float, default=-np.Inf,
                    help='minimum temperature (K)')
parser.add_argument('--max_logg', type=float, default=np.Inf,
                    help='maximum logg')
parser.add_argument('--min_logg', type=float, default=-np.Inf,
                    help='minimum logg')
parser.add_argument('--max_feh', type=float, default=np.Inf,
                    help='maximum [Fe/H]')
parser.add_argument('--min_feh', type=float, default=-np.Inf,
                    help='minimum [Fe/H]')
args = parser.parse_args()

output_path = args.output_path
processing_script = args.script
spec_dir = args.spec_dir
num_spec = args.num_spec
spectral_grid_name = args.grid
save_dir = args.save_dir
wave_grid_obs_file = args.obs_wave_file
max_num_spec = args.num_spec
wave_grid_synth_file = args.synth_wave_file
batch_size = args.batch_size
instrument_res = args.resolution
max_noise = args.noise
max_vrad = args.radial_vel
max_vrot = args.rotational_vel
max_teff = args.max_teff
min_teff = args.min_teff
max_logg = args.max_logg
min_logg = args.min_logg
max_feh = args.max_feh
min_feh = args.min_feh

with open('slurm_job_template.sh', 'r') as reader:
    with open(output_path, 'w') as writer:
        writer.write(reader.read())
        writer.write('\n')
        writer.write('python %s \\\n' % processing_script)
        writer.write('--spec_dir %s \\\n' % spec_dir)
        writer.write('--save_dir %s \\\n' % save_dir)
        writer.write('--obs_wave_file %s \\\n' % wave_grid_obs_file)
        writer.write('--grid %s \\\n' % spectral_grid_name)
        writer.write('--resolution %s \\\n' % instrument_res)
        writer.write('--obs_wave_file %s \\\n' % wave_grid_obs_file)
        writer.write('--synth_wave_file %s \\\n' % wave_grid_synth_file)
        writer.write('--num_spec %s \\\n' % num_spec)
        writer.write('--batch_size %s \\\n' % batch_size)
        writer.write('--radial_vel %s \\\n' % max_vrad)
        writer.write('--rotational_vel %s \\\n' % max_vrot)
        writer.write('--noise %s \\\n' % max_noise)
        if max_teff != np.Inf:
            writer.write('--max_teff %s \\\n' % max_teff)
        if min_teff != -np.Inf:
            writer.write('--min_teff %s \\\n' % min_teff)
        if max_logg != np.Inf:
            writer.write('--max_logg %s \\\n' % max_logg)
        if min_logg != -np.Inf:
            writer.write('--min_logg %s \\\n' % min_logg)
        if max_feh != np.Inf:
            writer.write('--max_feh %s \\\n' % max_feh)
        if min_feh != -np.Inf:
            writer.write('--min_feh %s' % min_feh)